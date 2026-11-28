"""Market data routes and service: validation, shaping, fail-loud behaviour. No real network calls."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services import market_service as ms

client = TestClient(app, base_url="http://127.0.0.1")  # the API answers only to local host names


@pytest.fixture(autouse=True)
def _fresh_cache():
    ms.clear_cache()
    yield
    ms.clear_cache()


def _ohlcv(n=40, start=100.0, step=0.5, freq="D", tz=None):
    idx = pd.date_range("2026-01-01", periods=n, freq=freq, tz=tz)
    close = start + np.arange(n) * step
    return pd.DataFrame({"Open": close - 0.2, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1_000_000 + np.arange(n)}, index=idx)


def _multi(symbols, **kw):
    return pd.concat({s: _ohlcv(start=100 + i * 10, **kw) for i, s in enumerate(symbols)}, axis=1)


def test_symbol_validation():
    assert ms.normalize_symbol(" aapl ") == "AAPL"
    assert ms.normalize_symbol("BRK-B") == "BRK-B"
    for bad in ["", "A B", "../etc", "AAPL;DROP", "X" * 20, "$AAPL"]:
        with pytest.raises(ms.InvalidSymbol):
            ms.normalize_symbol(bad)


def test_overview_shape_and_movers_sorted_by_absolute_move():
    universe = ms.settings.get_universe("US")
    symbols = [s for s, _ in ms.ETFS] + list(universe)
    with patch.object(ms, "_download", return_value=_multi(symbols)):
        body = client.get("/api/market/overview").json()
    assert [e["symbol"] for e in body["etfs"]] == ["SPY", "QQQ", "DIA", "IWM"]
    assert len(body["universe"]) == len(universe)
    assert len(body["movers"]) == 5
    moves = [abs(m["change_pct"]) for m in body["movers"]]
    assert moves == sorted(moves, reverse=True)
    q = body["universe"][0]
    assert {"price", "change_pct", "volume", "spark", "weight", "name"} <= set(q) and len(q["spark"]) == 30


def test_quotes_skip_symbols_without_data_but_fail_when_nothing_comes_back():
    two = _multi(["AAPL"])  # MSFT is missing from the frame
    with patch.object(ms, "_download", return_value=two):
        body = client.get("/api/market/quotes?symbols=AAPL,MSFT").json()
    assert [q["symbol"] for q in body["quotes"]] == ["AAPL"]
    ms.clear_cache()
    with patch.object(ms, "_download", return_value=pd.DataFrame()):
        r = client.get("/api/market/quotes?symbols=AAPL")
    assert r.status_code == 503 and "No price data" in r.json()["detail"]


def test_quotes_reject_bad_input():
    assert client.get("/api/market/quotes?symbols=AAPL,../x").status_code == 422
    assert client.get("/api/market/quotes?symbols=" + ",".join(["A"] * 41)).status_code == 422
    assert client.get("/api/market/quotes").status_code == 422


def test_history_returns_bars_and_aligned_spy():
    frames = {"AAPL": _ohlcv(60), "SPY": _ohlcv(60, start=500)}
    with patch.object(ms, "_download", side_effect=lambda syms, p, i: pd.concat({syms[0]: frames[syms[0]]}, axis=1)):
        body = client.get("/api/market/history/aapl?interval=1day&bars=30&spy=true").json()
    assert body["symbol"] == "AAPL" and len(body["bars"]) == 30
    assert {"t", "o", "h", "l", "c", "v"} <= set(body["bars"][0])
    assert len(body["spy"]) == 30 and body["spy"][0]["t"] == body["bars"][0]["t"]


def test_history_4h_is_resampled_from_hourly():
    hourly = _ohlcv(48, freq="h", tz="UTC")
    with patch.object(ms, "_download", return_value=pd.concat({"AAPL": hourly}, axis=1)):
        body = client.get("/api/market/history/AAPL?interval=4h&bars=20").json()
    assert 0 < len(body["bars"]) < 48
    first = body["bars"][0]
    assert first["h"] >= first["l"]


def test_history_unknown_interval_and_symbol_are_422():
    assert client.get("/api/market/history/AAPL?interval=3sec").status_code == 422
    assert client.get("/api/market/history/NOT%20A%20TICKER").status_code == 422


def test_history_network_failure_is_503_not_fake_data():
    with patch.object(ms.yf, "download", side_effect=ConnectionError("offline")):
        r = client.get("/api/market/history/AAPL")
    assert r.status_code == 503 and "Yahoo Finance" in r.json()["detail"]


def test_stock_has_stats_model_score_for_universe_only_and_headlines():
    with patch.object(ms, "_download", return_value=pd.concat({"AAPL": _ohlcv(260)}, axis=1)), \
         patch.object(ms, "_model_score", return_value={"probability": 0.52, "date": "2026-09-29", "zone": "wait zone"}), \
         patch.object(ms, "_headlines", return_value=[{"title": "x", "sentiment": "neutral"}]):
        body = client.get("/api/market/stock/AAPL").json()
    assert body["week52_high"] >= body["price"] >= body["week52_low"]
    assert body["model"]["zone"] == "wait zone" and body["headlines"]
    assert ms._model_score("ZZZZ") is None  # outside the universe: no invented score


def test_no_write_methods_on_market_routes():
    for path in ("/api/market/overview", "/api/market/quotes?symbols=AAPL", "/api/market/history/AAPL", "/api/market/stock/AAPL"):
        for method in ("post", "put", "delete"):
            assert getattr(client, method)(path).status_code == 405


def test_quotes_carry_a_stored_model_score_only_for_universe_stocks():
    score = {"probability": 0.61, "date": "2026-09-29", "zone": "buy zone"}
    with patch.object(ms, "_download", return_value=_multi(["AAPL", "QQQ"])), patch.object(ms, "_model_score", return_value=score):
        quotes = {q["symbol"]: q for q in client.get("/api/market/quotes?symbols=AAPL,QQQ").json()["quotes"]}
    assert quotes["AAPL"]["model"] == score
    assert quotes["QQQ"]["model"] is None  # not one of the 25: no invented score
