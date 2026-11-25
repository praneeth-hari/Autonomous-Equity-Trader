"""
src/ops/gate_review.py — Measure what the data-validation gate's spike rule is doing to the universe.

  python -m src.ops.gate_review                 # print the findings
  python -m src.ops.gate_review --markdown      # as the table used in docs/DATA_GATE_REVIEW.md

REPORT ONLY. It reads stored prices, never writes, and never changes the gate: the gate is part of
the frozen V1 configuration (see V1_FREEZE_REPORT.md).

For every day the spike rule would reject, it asks two questions that tell a real market event from a
bad data print:
  * Volume: did trading volume jump too? A bad print rarely comes with a volume surge.
  * Persistence: five trading days later, is the price still near the new level? A bad print reverts.
A day that passes both is labelled "looks real". This is a heuristic, not proof (it cannot read the news),
and each label is shown with its numbers so you can judge.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from config.settings import settings
from src.data.validation import _price_spike_masks, live_validation_lookback_days

REAL_VOLUME_RATIO = 2.0     # volume at least 2x its 20-day average
REAL_RETENTION = 0.5        # at least half of the move still there five trading days later
BAD_VOLUME_RATIO = 1.5      # volume no higher than the gate's own "normal volume" limit


@dataclass
class Event:
    ticker: str
    day: str
    move_pct: float
    threshold_pct: float
    volume_ratio: Optional[float]
    retention: Optional[float]
    verdict: str            # looks real | possible bad print | unclear
    excluded_until: str
    days_left: int          # from `today`; 0 when the window has ended


def classify(volume_ratio: Optional[float], retention: Optional[float]) -> str:
    if volume_ratio is not None and retention is not None and volume_ratio >= REAL_VOLUME_RATIO and retention >= REAL_RETENTION:
        return "looks real"
    if (volume_ratio is not None and volume_ratio <= BAD_VOLUME_RATIO) or (retention is not None and retention < 0.2):
        return "possible bad print"
    return "unclear"


def events_for(ticker: str, df: pd.DataFrame, today: date, lookback_days: Optional[int] = None) -> List[Event]:
    lookback = lookback_days if lookback_days is not None else live_validation_lookback_days()
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 6:
        return []
    pct, thresh, dyn, susp, _ = _price_spike_masks(df)
    flagged = (dyn | susp).fillna(False)
    prev_vol = df["volume"].shift(1).rolling(20, min_periods=1).mean()
    vol_ratio = df["volume"] / prev_vol.replace(0, float("nan"))
    out: List[Event] = []
    for i in df.index[flagged]:
        close = df["close"]
        move = float(close[i] / close[i - 1] - 1.0) if i > 0 else 0.0
        later = close[min(i + 5, len(df) - 1)]
        retention = float((later - close[i - 1]) / (close[i] - close[i - 1])) if i > 0 and close[i] != close[i - 1] else None
        vr = float(vol_ratio[i]) if pd.notna(vol_ratio[i]) else None
        d0 = pd.Timestamp(df["date"][i]).date()
        end = d0 + timedelta(days=lookback)
        out.append(Event(ticker, d0.isoformat(), move * 100, float(thresh[i]) * 100, vr, None if retention is None else float(retention),
                         classify(vr, retention), end.isoformat(), max(0, (end - today).days)))
    return out


def review(tickers: List[str], today: Optional[date] = None, load=None) -> List[Event]:
    from src.db import repository

    today = today or date.today()
    load = load or repository.get_market_data
    events: List[Event] = []
    for t in tickers:
        df = load(t)
        if df is not None and not df.empty:
            events += events_for(t, df, today)
    return sorted(events, key=lambda e: (e.ticker, e.day))


def days_excluded(events: List[Event], start: date, end: date) -> Dict[str, int]:
    """Calendar days in [start, end] during which each ticker is excluded. Overlapping windows are merged, never double counted."""
    by_ticker: Dict[str, List[tuple]] = {}
    for e in events:
        w0, w1 = datetime.fromisoformat(e.day).date(), datetime.fromisoformat(e.excluded_until).date()
        lo, hi = max(w0, start), min(w1, end)
        if hi > lo:
            by_ticker.setdefault(e.ticker, []).append((lo, hi))
    out: Dict[str, int] = {}
    for t, spans in by_ticker.items():
        spans.sort()
        total, cur_lo, cur_hi = 0, spans[0][0], spans[0][1]
        for lo, hi in spans[1:]:
            if lo <= cur_hi:
                cur_hi = max(cur_hi, hi)
            else:
                total += (cur_hi - cur_lo).days
                cur_lo, cur_hi = lo, hi
        out[t] = total + (cur_hi - cur_lo).days
    return out


def _fmt(e: Event) -> str:
    vr = "n/a" if e.volume_ratio is None else f"{e.volume_ratio:.1f}x"
    rt = "n/a" if e.retention is None else f"{e.retention * 100:.0f}%"
    return f"| {e.ticker} | {e.day} | {e.move_pct:+.1f}% | {e.threshold_pct:.0f}% | {vr} | {rt} | {e.verdict} | {e.excluded_until} |"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Report what the spike rule does to the universe.")
    p.add_argument("--markdown", action="store_true")
    a = p.parse_args(argv)
    today = date.today()
    tickers = list(settings.get_universe("US")) + [settings.get_benchmark("US")]
    events = review(tickers, today)
    freeze = date(2026, 9, 26)
    lost = days_excluded(events, freeze, freeze + timedelta(days=365))
    past = days_excluded(events, date(2022, 1, 1), freeze)
    print(f"Spike-rule review as of {today} | exclusion window per flagged day: {live_validation_lookback_days()} calendar days")
    print("| Ticker | Day | Move | Gate limit | Volume vs 20-day avg | Level kept after 5 days | Heuristic verdict | Excluded until |")
    print("|---|---|---|---|---|---|---|---|")
    for e in events:
        print(_fmt(e))
    print()
    print(f"Flagged days: {len(events)} | looks real: {sum(e.verdict == 'looks real' for e in events)} | "
          f"possible bad print: {sum(e.verdict == 'possible bad print' for e in events)} | unclear: {sum(e.verdict == 'unclear' for e in events)}")
    print("Calendar days each stock would have been excluded from 2022-01-01 to the freeze (2026-09-26, 1,729 days): " +
          (", ".join(f"{t} {d}" for t, d in sorted(past.items())) or "none"))
    print("Calendar days of the 12-month forward test (from 2026-09-26, 365 days) each stock is excluded: " +
          (", ".join(f"{t} {d}" for t, d in sorted(lost.items())) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
