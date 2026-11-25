"""The price schema flags impossible stored data, reports every violation at once, and never raises."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.schemas import validate_prices


def _frame(n=6):
    d = pd.bdate_range("2026-03-02", periods=n)
    c = [100.0 + i for i in range(n)]
    return pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "open": c, "high": [x + 1 for x in c], "low": [x - 1 for x in c],
                         "close": c, "volume": [1000.0] * n, "ticker": "XYZ"})


def test_clean_data_passes_and_extra_columns_are_fine():
    assert validate_prices(_frame()) == []


@pytest.mark.parametrize("mutate, expected", [
    (lambda f: f.__setitem__("close", [100, -5, 102, 103, 104, 105]), "close"),
    (lambda f: f.__setitem__("open", [0.0] + list(f["open"][1:])), "open"),
    (lambda f: f.__setitem__("volume", [1000, -1, 1000, 1000, 1000, 1000]), "volume"),
    (lambda f: f.__setitem__("high", [98.0] + list(f["high"][1:])), "high must be at least low"),
    (lambda f: f.__setitem__("close", [200.0] + list(f["close"][1:])), "close must lie between"),
])
def test_impossible_values_are_named(mutate, expected):
    f = _frame()
    mutate(f)
    out = validate_prices(f)
    assert out and any(expected in line for line in out), out


def test_duplicate_dates_are_caught():
    f = _frame()
    f.loc[3, "date"] = f.loc[2, "date"]
    out = validate_prices(f)
    assert any("each date may appear once" in line for line in out)
    assert len(out) == 1, "a whole-row rule must be reported once, not once per column"


def test_all_violations_are_reported_together_not_just_the_first():
    f = _frame()
    f.loc[1, "close"] = -1.0
    f.loc[2, "volume"] = -9.0
    f.loc[3, "open"] = 0.0
    assert len(validate_prices(f)) >= 3


def test_violation_lines_say_where_to_look():
    f = _frame()
    f.loc[2, "close"] = -1.0
    assert any("2026-03-04" in line for line in validate_prices(f))


def test_missing_volume_is_allowed_but_missing_prices_are_not():
    f = _frame()
    f.loc[1, "volume"] = None
    assert validate_prices(f) == []
    f.loc[1, "close"] = None
    assert validate_prices(f)


def test_garbage_input_returns_messages_instead_of_raising():
    assert validate_prices(pd.DataFrame({"date": ["not a date"], "close": ["x"]}))  # missing columns and bad values: reported


def test_out_of_order_dates_are_reported_not_silently_fixed():
    f = _frame().iloc[::-1].reset_index(drop=True)  # newest first
    assert any("increasing order" in line for line in validate_prices(f))
