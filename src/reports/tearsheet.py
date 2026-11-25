"""
src/reports/tearsheet.py — A full performance report of the paper account against SPY (QuantStats).

  python -m src.reports.tearsheet            # writes reports/tearsheet_<date>.html

Project rules applied here:
  * Net, never gross: the account's own daily value already includes every simulated cost.
  * SPY buy-and-hold is always shown beside the strategy.
  * The report carries the "optimistic, real results likely worse" label in its title and a banner.
  * Fewer than 30 daily returns means no report: ratios on a few days are noise, not information.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

os.environ.setdefault("MPLBACKEND", "Agg")  # no windows: this runs unattended

from config.settings import settings

ROOT = Path(__file__).resolve().parents[2]
MIN_DAYS = 30
BANNER = (
    '<div style="background:#fff4e0;border:1px solid #e0a43a;color:#6b4a0c;padding:12px 16px;margin:12px;'
    'border-radius:8px;font:14px sans-serif">'
    "<b>Paper trading only.</b> Returns are net of the simulated 0.2% cost per trade and are compared with SPY buy-and-hold. "
    "<b>Optimistic: real results are likely worse.</b> Nothing here is financial advice.</div>"
)


class NotEnoughHistory(ValueError):
    """Too few daily returns for statistics to mean anything."""


def load_returns(market: str = "US") -> Tuple[pd.Series, pd.Series]:
    """Daily returns of the account and of SPY on the same dates."""
    from src.db import repository

    snaps = repository.get_portfolio_snapshots(limit=5000, market=market)
    if not snaps:
        raise NotEnoughHistory("There are no portfolio snapshots yet.")
    equity = pd.Series({pd.Timestamp(s["run_date"]): float(s["total_value"]) for s in snaps}).sort_index()
    spy = repository.get_market_data(settings.get_benchmark(market))
    if spy is None or spy.empty:
        raise NotEnoughHistory("There is no stored SPY history to compare with.")
    close = pd.Series(spy["close"].values, index=pd.to_datetime(spy["date"]).dt.tz_localize(None)).sort_index()
    bench = close.reindex(equity.index, method="ffill", limit=3)
    both = pd.concat([equity.pct_change(), bench.pct_change()], axis=1, keys=["Strategy", "SPY"]).dropna()
    return both["Strategy"], both["SPY"]


def build(returns: pd.Series, benchmark: pd.Series, out_path: Path, min_days: int = MIN_DAYS) -> Path:
    """Write the HTML report. Raises NotEnoughHistory below `min_days` returns."""
    n = int(len(returns))
    if n < min_days:
        raise NotEnoughHistory(
            f"Only {n} daily return(s). A report needs at least {min_days}; below that the ratios are noise. Try again later.")
    import quantstats as qs  # imported late: pulls matplotlib, so keep it out of every other import path

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    qs.reports.html(
        returns, benchmark=benchmark, output=str(out_path), rf=0.0,
        title="Paper Trader vs SPY, net of costs. OPTIMISTIC: real results likely worse.",
        benchmark_title="SPY buy-and-hold", strategy_title="Paper Trader (net)",
    )
    html = out_path.read_text(encoding="utf-8", errors="replace")
    out_path.write_text(html.replace("<body>", "<body>" + BANNER, 1) if "<body>" in html else BANNER + html, encoding="utf-8")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Write a performance tear sheet against SPY.")
    p.add_argument("--out", help="output file (default reports/tearsheet_<today>.html)")
    p.add_argument("--min-days", type=int, default=MIN_DAYS)
    a = p.parse_args(argv)
    out = Path(a.out) if a.out else ROOT / "reports" / f"tearsheet_{date.today().isoformat()}.html"
    try:
        returns, bench = load_returns()
        print("Wrote " + str(build(returns, bench, out, a.min_days)))
        return 0
    except NotEnoughHistory as exc:
        print(f"No tear sheet written: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
