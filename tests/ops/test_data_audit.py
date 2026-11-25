"""Data audit: holes are measured in consecutive TRADING SESSIONS (weekends do not break a run)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.ops import data_audit as da
from src.data.validation import _get_nyse_trading_days


def _bars(sessions):
    n = len(sessions)
    c = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"date": sessions, "open": c, "high": [x + 1 for x in c], "low": [x - 1 for x in c], "close": c, "volume": [1000.0] * n})


def _sessions(a, b):
    return sorted(_get_nyse_trading_days(a, b))


def test_longest_run_counts_sessions_across_weekends():
    sessions = ["a", "b", "c", "d", "e", "f", "g", "h"]
    assert da.longest_run(sessions, {"a", "h"}) == (6, "b", "g")
    assert da.longest_run(sessions, set(sessions)) == (0, None, None)
    assert da.longest_run(sessions, {"c", "f"}) == (2, "a", "b")  # three runs of 2: the first one wins
    assert da.longest_run(sessions, {"a", "b", "c", "f", "g"}) == (2, "d", "e")


def test_a_clean_history_is_ok():
    s = _sessions("2026-01-02", "2026-03-31")
    r = da.audit_ticker("XYZ", _bars(s), today=date(2026, 3, 31))
    assert r.ok and r.longest_hole == 0 and r.missing_sessions == 0 and r.stale_sessions == 0


def test_a_gap_that_spans_weekends_is_found_as_one_hole():
    s = _sessions("2026-01-02", "2026-03-31")
    hole = s[20:28]                                   # 8 consecutive sessions, crossing a weekend
    r = da.audit_ticker("XYZ", _bars([x for x in s if x not in hole]), today=date(2026, 3, 31))
    assert r.longest_hole == 8 and r.hole_range == f"{hole[0]} to {hole[-1]}" and not r.ok
    assert any("hole of 8 consecutive missing sessions" in p for p in r.problems())


def test_a_short_gap_is_not_a_hole():
    s = _sessions("2026-01-02", "2026-03-31")
    r = da.audit_ticker("XYZ", _bars([x for x in s if x not in s[20:23]]), today=date(2026, 3, 31))
    assert r.longest_hole == 3 and r.ok


def test_market_holidays_are_not_missing_data():
    """Good Friday 2026-04-03 must not count as a missing session."""
    s = _sessions("2026-03-02", "2026-04-30")
    assert "2026-04-03" not in s
    assert da.audit_ticker("XYZ", _bars(s), today=date(2026, 4, 30)).missing_sessions == 0


def test_a_stale_history_is_flagged_with_its_age_in_sessions():
    s = _sessions("2026-01-02", "2026-03-02")
    r = da.audit_ticker("XYZ", _bars(s), today=date(2026, 3, 20))
    assert r.stale_sessions >= 10 and not r.ok and any("sessions old" in p for p in r.problems())


def test_schema_violations_and_empty_data_are_reported():
    s = _sessions("2026-01-02", "2026-02-27")
    f = _bars(s)
    f.loc[3, "close"] = -1.0
    r = da.audit_ticker("XYZ", f, today=date(2026, 2, 27))
    assert not r.ok and any("close" in v for v in r.violations)
    assert da.audit_ticker("EMPTY", pd.DataFrame(), today=date(2026, 2, 27)).violations == ["no stored data"]


def test_audit_reads_only_and_returns_one_result_per_ticker():
    s = _sessions("2026-01-02", "2026-02-27")
    out = da.audit(["AAA", "BBB"], today=date(2026, 2, 27), load=lambda t: _bars(s))
    assert [r.ticker for r in out] == ["AAA", "BBB"] and all(r.ok for r in out)
