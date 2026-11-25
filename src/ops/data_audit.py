"""
src/ops/data_audit.py — Audit every stored price history: schema, staleness and holes.

  python -m src.ops.data_audit

Report only: it reads stored prices and never changes them or the validation gate.

What it checks per ticker:
  * Schema: the sanity rules in src/data/schemas.py (all violations at once).
  * Freshness: how old the newest bar is, in trading sessions.
  * Holes: runs of consecutive MISSING NYSE sessions. A weekend does not break a run here, which is exactly
    what the live gap check gets wrong (see docs/DATA_GATE_REVIEW.md). A run of 6 or more is a real hole.

Exit code 0 when everything is clean, 1 when any ticker has a violation, a stale bar or a hole.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional

import pandas as pd

from config.settings import settings

HOLE_SESSIONS = 6      # the documented rejection length of the live gap check
STALE_SESSIONS = 5     # newest bar older than this many sessions


@dataclass
class TickerAudit:
    ticker: str
    rows: int = 0
    first: Optional[str] = None
    last: Optional[str] = None
    violations: List[str] = field(default_factory=list)
    stale_sessions: int = 0
    longest_hole: int = 0
    hole_range: Optional[str] = None
    missing_sessions: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations and self.stale_sessions <= STALE_SESSIONS and self.longest_hole < HOLE_SESSIONS

    def problems(self) -> List[str]:
        out = list(self.violations)
        if self.longest_hole >= HOLE_SESSIONS:
            out.append(f"hole of {self.longest_hole} consecutive missing sessions ({self.hole_range})")
        if self.stale_sessions > STALE_SESSIONS:
            out.append(f"newest bar is {self.stale_sessions} sessions old")
        return out


def longest_run(sessions: List[str], present: set) -> tuple:
    """(length, first, last) of the longest run of consecutive sessions missing from `present`."""
    best = (0, None, None)
    run_start, run = None, 0
    for s in sessions:
        if s in present:
            run, run_start = 0, None
            continue
        run_start = run_start or s
        run += 1
        if run > best[0]:
            best = (run, run_start, s)
    return best


def audit_ticker(ticker: str, df: pd.DataFrame, today: Optional[date] = None) -> TickerAudit:
    from src.data.schemas import validate_prices
    from src.data.validation import _get_nyse_trading_days

    today = today or date.today()
    res = TickerAudit(ticker=ticker, rows=int(len(df)))
    if df is None or df.empty:
        res.violations.append("no stored data")
        return res
    dates = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None).dropna()
    res.first, res.last = dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")
    res.violations = validate_prices(df)
    sessions = sorted(_get_nyse_trading_days(res.first, today.strftime("%Y-%m-%d")))
    present = set(dates.dt.strftime("%Y-%m-%d"))
    inside = [s for s in sessions if s <= res.last]
    missing = [s for s in inside if s not in present]
    res.missing_sessions = len(missing)
    n, a, b = longest_run(inside, present)
    res.longest_hole, res.hole_range = n, (f"{a} to {b}" if a else None)
    res.stale_sessions = sum(1 for s in sessions if s > res.last)
    return res


def audit(tickers: List[str], today: Optional[date] = None, load: Optional[Callable] = None) -> List[TickerAudit]:
    from src.db import repository

    load = load or repository.get_market_data
    return [audit_ticker(t, load(t), today) for t in tickers]


def main() -> int:
    tickers = list(settings.get_universe("US")) + [settings.get_benchmark("US")]
    results = audit(tickers)
    bad = [r for r in results if not r.ok]
    print(f"Stored price audit: {len(results)} tickers, {len(bad)} with problems")
    for r in results:
        status = "ok" if r.ok else "PROBLEM"
        print(f"  {r.ticker:<6} {status:<8} {r.rows} rows {r.first} to {r.last}" + ("" if r.ok else " | " + "; ".join(r.problems())))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
