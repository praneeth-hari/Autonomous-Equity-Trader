"""Tear sheet: refuses small samples, labels itself honestly, and shows SPY beside the strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.reports import tearsheet as ts


def _series(n, seed=1):
    idx = pd.bdate_range("2026-01-02", periods=n)
    rng = np.random.default_rng(seed)
    return (pd.Series(rng.normal(0.0003, 0.01, n), index=idx, name="Strategy"),
            pd.Series(rng.normal(0.0004, 0.009, n), index=idx, name="SPY"))


def test_refuses_fewer_than_30_returns_and_says_why(tmp_path):
    r, b = _series(12)
    with pytest.raises(ts.NotEnoughHistory, match="Only 12 daily return"):
        ts.build(r, b, tmp_path / "t.html")
    assert not (tmp_path / "t.html").exists()


def test_writes_a_labelled_report_with_the_spy_comparison(tmp_path):
    r, b = _series(60)
    out = ts.build(r, b, tmp_path / "reports" / "t.html")
    html = out.read_text(encoding="utf-8")
    assert "OPTIMISTIC" in html.upper() and "real results" in html
    assert "net of the simulated 0.2% cost" in html and "Paper trading only" in html
    assert "SPY buy-and-hold" in html and "Paper Trader (net)" in html
    assert html.index("Paper trading only") < html.index("SPY buy-and-hold")  # the banner comes first


def test_returns_use_the_accounts_own_net_values_and_align_with_spy(monkeypatch):
    import src.db.repository as repo

    days = pd.bdate_range("2026-03-02", periods=5)
    snaps = [{"run_date": d.strftime("%Y-%m-%d"), "total_value": v} for d, v in zip(days, [10000, 10100, 10050, 10200, 10200])]
    spy = pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "close": [500.0, 505.0, 504.0, 510.0, 509.0]})
    monkeypatch.setattr(repo, "get_portfolio_snapshots", lambda limit=0, market="US": snaps)
    monkeypatch.setattr(repo, "get_market_data", lambda t: spy)
    r, b = ts.load_returns()
    assert len(r) == len(b) == 4 and list(r.index) == list(b.index)
    assert r.iloc[0] == pytest.approx(0.01) and b.iloc[0] == pytest.approx(0.01)


def test_no_snapshots_or_no_spy_is_a_clear_message_not_a_crash(monkeypatch):
    import src.db.repository as repo

    monkeypatch.setattr(repo, "get_portfolio_snapshots", lambda limit=0, market="US": [])
    with pytest.raises(ts.NotEnoughHistory, match="no portfolio snapshots"):
        ts.load_returns()


def test_cli_exits_non_zero_with_a_message_when_there_is_too_little_history(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ts, "load_returns", lambda *a, **k: _series(5))
    assert ts.main(["--out", str(tmp_path / "x.html")]) == 1
    assert "No tear sheet written" in capsys.readouterr().out
