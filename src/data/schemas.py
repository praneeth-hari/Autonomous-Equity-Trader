"""
src/data/schemas.py — The shape stored daily price data must have, written down once (pandera).

These are the same sanity rules the validation gate applies to NEW data (project rule: reject impossible
values): positive prices, high >= low, close inside the day's range, volume >= 0. Declaring them as a schema
lets the audit (src/ops/data_audit.py) re-check everything already STORED, in one place, and report every
violation at once instead of stopping at the first.

This module does not change what the gate accepts or rejects. It only describes and re-checks.
"""

from __future__ import annotations

from typing import List

import pandas as pd

PRICE_COLUMNS = ["open", "high", "low", "close"]


def price_schema():
    """pandera schema for one ticker's daily bars (date as datetime, one row per day)."""
    import pandera.pandas as pa

    price = lambda: pa.Column(float, pa.Check.gt(0), nullable=False, coerce=True)  # noqa: E731
    return pa.DataFrameSchema(
        {
            "date": pa.Column("datetime64[ns]", nullable=False, coerce=True),
            "open": price(),
            "high": price(),
            "low": price(),
            "close": price(),
            "volume": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        },
        checks=[
            pa.Check(lambda d: d["high"] >= d["low"], error="high must be at least low"),
            pa.Check(lambda d: (d["close"] <= d["high"]) & (d["close"] >= d["low"]), error="close must lie between low and high"),
            pa.Check(lambda d: ~d["date"].duplicated(), error="each date may appear once"),
            pa.Check(lambda d: d["date"].is_monotonic_increasing, error="dates must be in increasing order"),
        ],
        strict=False,  # extra columns (ticker and so on) are fine
    )


def validate_prices(df: pd.DataFrame) -> List[str]:
    """Every violation as a readable line (empty list = the data is fine). Never raises on bad data."""
    import pandera.pandas as pa

    frame = df.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None)  # parsed, never re-ordered
    try:
        price_schema().validate(frame, lazy=True)
        return []
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases.copy()
        # A rule that spans the whole row (high >= low, unique dates...) is reported once, not once per column.
        cases["label"] = cases.apply(lambda r: r["column"] if r["schema_context"] == "Column" and isinstance(r["column"], str) else "", axis=1)
        out = []
        for (label, check), group in cases.groupby(["label", "check"], dropna=False):
            rows = sorted({int(i) for i in group["index"].dropna().tolist()})
            dates = [str(frame["date"].iloc[i].date()) for i in rows[:3] if 0 <= i < len(frame) and pd.notna(frame["date"].iloc[i])]
            where = f" (for example {', '.join(dates)})" if dates else ""
            who = f"{label}: " if label else ""
            out.append(f"{who}{check} failed on {len(rows) or len(group)} row(s){where}")
        return out
    except pa.errors.SchemaError as exc:
        return [str(exc)[:200]]
