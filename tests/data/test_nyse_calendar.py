"""The data check must use the real NYSE calendar, not pandas' federal-holiday list."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import src.data.validation as v


@pytest.mark.parametrize("day, is_trading", [
    ("2025-04-18", False),   # Good Friday: closed, but NOT a federal holiday
    ("2026-04-03", False),   # Good Friday
    ("2025-01-09", False),   # one-off national day of mourning
    ("2025-06-19", False),   # Juneteenth
    ("2025-07-04", False),   # Independence Day
    ("2025-10-13", True),    # Columbus Day: a federal holiday, but the market is OPEN
    ("2025-11-11", True),    # Veterans Day: a federal holiday, but the market is OPEN
    ("2025-11-28", True),    # day after Thanksgiving (half day)
    ("2025-04-17", True),
])
def test_known_days(day, is_trading):
    assert (day in v._get_nyse_trading_days(day, day)) is is_trading


def test_the_legacy_function_is_the_one_that_was_wrong():
    """Documents why it was replaced: it called Columbus Day closed and Good Friday open."""
    legacy = v._legacy_trading_days("2025-04-18", "2025-04-18") | v._legacy_trading_days("2025-10-13", "2025-10-13")
    assert "2025-04-18" in legacy and "2025-10-13" not in legacy


def test_a_year_has_the_expected_number_of_sessions():
    assert len(v._get_nyse_trading_days("2025-01-01", "2025-12-31")) == 250  # 2025 had 250 NYSE sessions


def test_inclusive_ends_and_reversed_or_far_future_ranges_do_not_crash():
    assert v._get_nyse_trading_days("2025-06-02", "2025-06-02") == {"2025-06-02"}
    assert v._get_nyse_trading_days("2025-06-10", "2025-06-02") == set()
    assert v._get_nyse_trading_days("2040-01-01", "2040-01-31") == set()  # outside the calendar: empty, not an exception


def test_a_session_range_after_the_old_default_calendar_end_still_works():
    """The calendar library defaults to ending about a year ahead; ours is fixed wide so it never expires."""
    assert "2030-06-03" in v._get_nyse_trading_days("2030-06-01", "2030-06-07")


def test_falls_back_to_the_legacy_calendar_when_the_library_is_unavailable(caplog):
    with patch.object(v, "_NYSE_CALENDAR", None), patch.dict("sys.modules", {"exchange_calendars": None}):
        days = v._get_nyse_trading_days("2025-06-02", "2025-06-06")
    assert days == {"2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06"}
    assert "unavailable" in caplog.text
    v._NYSE_CALENDAR = None  # let later tests reload the real one


def _prices(days):
    n = len(days)
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.003, n))
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.002, "low": close * 0.998, "close": close, "volume": 1_000_000.0, "ticker": "XYZ"})


def test_no_false_gap_warning_around_good_friday_and_the_stock_still_passes():
    days = [d for d in pd.bdate_range("2025-03-20", "2025-05-01").strftime("%Y-%m-%d") if d != "2025-04-18"]  # real data skips Good Friday
    res = v.validate_ticker_data(_prices(days), ticker="XYZ")
    assert res.is_valid and not any("unexplained missing" in w for w in res.warnings)


def test_a_genuine_hole_is_still_reported():
    days = [d for d in pd.bdate_range("2025-03-20", "2025-05-01").strftime("%Y-%m-%d") if d not in ("2025-04-18", "2025-04-09", "2025-04-10")]
    res = v.validate_ticker_data(_prices(days), ticker="XYZ")
    assert any("2025-04-09" in w and "2025-04-10" in w for w in res.warnings)


def _eight_missing_sessions_frame():
    missing = set(pd.bdate_range("2025-04-21", "2025-04-30").strftime("%Y-%m-%d"))  # 8 consecutive sessions
    days = [d for d in pd.bdate_range("2025-03-20", "2025-05-12").strftime("%Y-%m-%d") if d != "2025-04-18" and d not in missing]
    return _prices(days)


def test_the_calendar_change_does_not_alter_what_the_gap_check_decides():
    """Same data, old calendar vs real calendar: the same pass/fail and the same error count."""
    frame = _eight_missing_sessions_frame()
    new = v.validate_ticker_data(frame.copy(), ticker="XYZ")
    with patch.object(v, "_get_nyse_trading_days", v._legacy_trading_days):
        old = v.validate_ticker_data(frame.copy(), ticker="XYZ")
    assert (new.is_valid, len(new.errors)) == (old.is_valid, len(old.errors))


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN BUG, deliberately not fixed (the gate is frozen; see docs/DATA_GATE_REVIEW.md): the gap check is documented to "
    "reject 6+ consecutive missing sessions, but it only treats dates exactly one calendar day apart as consecutive, so a "
    "weekend splits every gap and no run can exceed 5. This test starts passing (and then fails, because strict) the day it is fixed."))
def test_eight_consecutive_missing_sessions_should_be_rejected():
    res = v.validate_ticker_data(_eight_missing_sessions_frame(), ticker="XYZ")
    assert res.is_valid is False
