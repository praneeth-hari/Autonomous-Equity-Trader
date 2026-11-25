"""The gate review: tells a volume-backed, lasting move from a one-day bad print, and counts exclusion days correctly."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.ops import gate_review as gr


def _prices(n=80, spike_at=60, spike=0.30, volume_mult=6.0, revert=False, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.004, n))
    vol = np.full(n, 1_000_000.0)
    close[spike_at:] *= 1 + spike
    vol[spike_at] *= volume_mult
    if revert:
        close[spike_at + 1:] /= 1 + spike  # the print was a one-day glitch
    return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=n, freq="B").strftime("%Y-%m-%d"), "close": close, "volume": vol, "open": close, "high": close, "low": close})


def test_a_volume_backed_lasting_move_looks_real():
    ev = gr.events_for("XYZ", _prices(), date(2026, 6, 1), lookback_days=724)
    assert len(ev) == 1 and ev[0].verdict == "looks real"
    assert ev[0].volume_ratio >= 5 and ev[0].retention >= 0.9


def test_a_one_day_print_on_normal_volume_looks_bad():
    ev = gr.events_for("XYZ", _prices(volume_mult=1.0, revert=True), date(2026, 6, 1), lookback_days=724)
    # The glitch day and the snap back the next day are both flagged; the glitch day is the first.
    assert len(ev) == 2 and ev[0].verdict == "possible bad print"


def test_a_quiet_series_has_no_events():
    assert gr.events_for("XYZ", _prices(spike=0.0), date(2026, 6, 1)) == []


def test_exclusion_window_runs_for_the_lookback_from_the_flagged_day():
    e = gr.events_for("XYZ", _prices(), date(2026, 6, 1), lookback_days=100)[0]
    start = date.fromisoformat(e.day)
    assert (date.fromisoformat(e.excluded_until) - start).days == 100


def test_overlapping_windows_are_merged_not_double_counted():
    mk = lambda day, until: gr.Event("A", day, 25, 20, 5, 1, "looks real", until, 0)
    events = [mk("2026-01-01", "2026-01-31"), mk("2026-01-15", "2026-02-14"), mk("2026-06-01", "2026-06-11")]
    out = gr.days_excluded(events, date(2026, 1, 1), date(2026, 12, 31))
    assert out == {"A": 44 + 10}  # Jan 1 - Feb 14 (44 days) plus Jun 1 - Jun 11 (10 days)


def test_days_are_clipped_to_the_requested_period():
    e = gr.Event("A", "2026-01-01", 25, 20, 5, 1, "looks real", "2026-12-31", 0)
    assert gr.days_excluded([e], date(2026, 6, 1), date(2026, 6, 30)) == {"A": 29}
    assert gr.days_excluded([e], date(2027, 1, 1), date(2027, 3, 1)) == {}


def test_review_only_reads_and_never_needs_the_database():
    seen = []

    def load(t):
        seen.append(t)
        return _prices()

    out = gr.review(["AAA", "BBB"], date(2026, 6, 1), load=load)
    assert seen == ["AAA", "BBB"] and {e.ticker for e in out} == {"AAA", "BBB"}
