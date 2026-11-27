"""Skip markers for the few tests that need data git does not track.

Price history (the SQLite database), the delisted-stock CSVs and older saved models are kept only on the
machine that runs the system. On a fresh clone or in CI these tests are skipped with a reason instead of
failing for a reason that has nothing to do with the code. On the trading machine they run as before.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = ROOT / "data" / "processed" / "trader.db"
SURVIVORSHIP_DIR = ROOT / "data" / "raw" / "survivorship"
MODELS_DIR = ROOT / "data" / "models"


def _has_price_history() -> bool:
    if not PRODUCTION_DB.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{PRODUCTION_DB.as_posix()}?mode=ro", uri=True)
        try:
            return con.execute("SELECT COUNT(*) FROM market_data").fetchone()[0] > 0
        finally:
            con.close()
    except sqlite3.Error:
        return False


needs_price_history = pytest.mark.skipif(
    not _has_price_history(),
    reason="needs stored price history in data/processed/trader.db (not in git)",
)
needs_survivorship_csvs = pytest.mark.skipif(
    not all((SURVIVORSHIP_DIR / f"{t}.csv").exists() for t in ("FRCB", "TWTR", "CELG")),
    reason="needs data/raw/survivorship/{FRCB,TWTR,CELG}.csv (not in git)",
)
needs_saved_baseline_models = pytest.mark.skipif(
    not any(MODELS_DIR.glob("logistic_regression_baseline_v1_*.joblib")),
    reason="needs saved baseline models in data/models (only the active model is in git)",
)
