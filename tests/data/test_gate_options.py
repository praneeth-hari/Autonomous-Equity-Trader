"""The two data-gate fixes from docs/DATA_GATE_REVIEW.md: off by default (frozen V1 unchanged), correct when on."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import src.data.validation as v
from config.settings import settings


def _series(n=60, spike_at=45, move=0.25, spike_volume=1_000_000.0, seed=5):
    """Quiet prices (about 0.3% a day) on 1M volume, with one big move on one day."""
    days = pd.bdate_range("2025-01-02", periods=n).strftime("%Y-%m-%d").tolist()
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.003, n)
    rets[spike_at] = move
    close = 100 * np.cumprod(1 + rets)
    vol = np.full(n, 1_000_000.0)
    vol[spike_at] = spike_volume
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": vol, "ticker": "XYZ"}), days[spike_at]


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(settings, "gate_spike_volume_exception", False)
    monkeypatch.setattr(settings, "gate_gaps_count_sessions", False)


@pytest.fixture
def fixed(monkeypatch):
    monkeypatch.setattr(settings, "gate_spike_volume_exception", True)
    monkeypatch.setattr(settings, "gate_spike_volume_ratio", 2.0)
    monkeypatch.setattr(settings, "gate_gaps_count_sessions", True)


def test_both_fixes_are_off_by_default():
    fresh = type(settings)()
    assert fresh.gate_spike_volume_exception is False and fresh.gate_gaps_count_sessions is False


# ── Option B: volume exception for the spike rule ──────────────────────────────

def test_frozen_rule_rejects_a_real_earnings_move(frozen):
    df, day = _series(move=-0.24, spike_volume=6_000_000.0)       # like UNH 2025-04-17: -22% on 5x volume
    res = v.validate_ticker_data(df, ticker="XYZ")
    assert not res.is_valid and day in res.errors[0]


def test_fixed_rule_accepts_a_spike_on_heavy_volume(fixed):
    df, _ = _series(move=-0.24, spike_volume=6_000_000.0)
    assert v.validate_ticker_data(df, ticker="XYZ").is_valid


def test_fixed_rule_still_rejects_a_spike_on_ordinary_volume(fixed):
    df, day = _series(move=0.23, spike_volume=1_400_000.0)        # like the TSLA 2024-09-19 print: 1.4x volume
    res = v.validate_ticker_data(df, ticker="XYZ")
    assert not res.is_valid and day in res.errors[0]


def test_the_exception_needs_the_full_ratio(fixed):
    df, _ = _series(move=0.23, spike_volume=1_990_000.0)          # just under 2x
    assert not v.validate_ticker_data(df, ticker="XYZ").is_valid


def test_the_volume_exception_uses_no_future_rows(fixed):
    """Changing volume AFTER the spike must not change whether the spike day is accepted."""
    df, _ = _series(move=-0.24, spike_volume=6_000_000.0)
    later = df.copy()
    later.loc[46:, "volume"] = 50_000_000.0
    a = v._price_spike_masks(df)[2]
    b = v._price_spike_masks(later)[2]
    assert a.iloc[:46].equals(b.iloc[:46])


def test_heavy_volume_does_not_excuse_impossible_values(fixed):
    df, _ = _series(move=-0.24, spike_volume=6_000_000.0)
    df.loc[10, "low"] = df.loc[10, "high"] * 2                    # low above high: impossible
    assert not v.validate_ticker_data(df, ticker="XYZ").is_valid


def test_point_in_time_validation_also_honours_the_exception(fixed):
    df, _ = _series(move=-0.24, spike_volume=6_000_000.0)
    res = v.validate_ticker_data_point_in_time(df, ticker="XYZ")
    assert res.is_valid and res.excluded_windows == []


# ── Gap counting in trading sessions ───────────────────────────────────────────

def _prices(days):
    close = 100 * np.cumprod(1 + np.random.default_rng(3).normal(0, 0.003, len(days)))
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": 1_000_000.0, "ticker": "XYZ"})


def _missing_sessions_frame(first, last):
    missing = set(pd.bdate_range(first, last).strftime("%Y-%m-%d"))
    days = [d for d in pd.bdate_range("2025-03-20", "2025-05-30").strftime("%Y-%m-%d")
            if d != "2025-04-18" and d not in missing]                # 2025-04-18 is Good Friday
    return _prices(days)


def test_frozen_rule_lets_eight_missing_sessions_pass(frozen):
    assert v.validate_ticker_data(_missing_sessions_frame("2025-04-21", "2025-04-30"), ticker="XYZ").is_valid


def test_fixed_rule_rejects_eight_consecutive_missing_sessions_across_a_weekend(fixed):
    res = v.validate_ticker_data(_missing_sessions_frame("2025-04-21", "2025-04-30"), ticker="XYZ")
    assert not res.is_valid
    assert "8 unexplained missing" in res.errors[0]


def test_fixed_rule_still_passes_five_missing_sessions(fixed):
    res = v.validate_ticker_data(_missing_sessions_frame("2025-04-21", "2025-04-25"), ticker="XYZ")
    assert res.is_valid and any("5 unexplained missing" in w for w in res.warnings)


def test_a_holiday_inside_a_gap_does_not_split_it(fixed):
    """Missing 14-17 Apr and 21-22 Apr: six sessions, with Good Friday (closed) and a weekend in between."""
    missing = set(pd.bdate_range("2025-04-14", "2025-04-22").strftime("%Y-%m-%d"))
    days = [d for d in pd.bdate_range("2025-03-20", "2025-05-30").strftime("%Y-%m-%d") if d != "2025-04-18" and d not in missing]
    res = v.validate_ticker_data(_prices(days), ticker="XYZ")
    assert not res.is_valid and "6 unexplained missing" in res.errors[0]


def test_backtest_validation_keeps_gaps_as_warnings(fixed):
    """Point-in-time (backtest) validation is not changed to reject on gaps: that would silently drop stocks
    with old holes from every backtest, which needs its own decision."""
    res = v.validate_ticker_data_point_in_time(_missing_sessions_frame("2025-04-21", "2025-04-30"), ticker="XYZ")
    assert res.is_valid and any(w.startswith("CRITICAL:") for w in res.warnings)
