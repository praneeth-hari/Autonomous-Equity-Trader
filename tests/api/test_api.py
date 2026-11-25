"""Read-only API: shape, safety (GET only), honesty labels, fail-loud behavior."""

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_module
from src.api.app import app

client = TestClient(app)


def test_status_reports_locked_rules_and_paper_only():
    body = client.get("/api/status").json()
    assert body["paper_only"] is True
    assert body["rules"]["buy_bar"] == 0.60
    assert body["rules"]["stop_loss"] in (-0.08, 0.08, -8.0, 8.0)
    assert body["benchmark"] == "SPY"


def test_overview_has_spy_curve_and_optimistic_label():
    body = client.get("/api/overview").json()
    assert "optimistic" in body["label"].lower()
    assert body["curve"], "curve must hold at least the starting point"
    assert {"date", "My Portfolio", "SPY Benchmark"} <= set(body["curve"][0])


def test_backtests_show_spy_beside_strategy_and_label():
    body = client.get("/api/backtests").json()
    assert "optimistic" in body["label"].lower()
    assert body["net_of_cost_pct_per_trade"] == 0.2
    for period in body["periods"]:
        assert "strategy" in period and "spy_buy_hold" in period


def test_trades_endpoint_validates_limit():
    assert client.get("/api/trades?limit=0").status_code == 422
    assert client.get("/api/trades?limit=5").status_code == 200


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_endpoints(method):
    for path in ("/api/overview", "/api/trades", "/api/status", "/api/portfolio"):
        assert getattr(client, method)(path).status_code == 405


def test_failing_reader_returns_503_not_fake_data(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(api_module.dl, "get_portfolio_summary", boom)
    r = client.get("/api/overview")
    assert r.status_code == 503
    assert "db down" in r.json()["detail"]


def test_clean_makes_nan_json_safe():
    assert api_module._clean(float("nan")) is None
    assert api_module._clean({"a": float("inf")}) == {"a": None}


def test_cors_only_allows_localhost_dev_server():
    r = client.options("/api/status", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
