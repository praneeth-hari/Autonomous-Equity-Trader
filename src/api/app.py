"""
src/api/app.py — Read-only FastAPI layer for the new frontend.

Rules (see docs/ENGINEERING_RULES.md):
  * Read-only: GET endpoints only. No trading, no broker, no model promotion.
  * Local only: CORS allows the Vite dev server on localhost, nothing else.
  * Net, never gross: every backtest payload carries the SPY comparison and the
    "optimistic" label.
  * Fail loud: a failing reader returns HTTP 503 with the reason, never fake data.

Run:  uvicorn src.api.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from dashboard import data_loader as dl

logger = logging.getLogger(__name__)

OPTIMISTIC_LABEL = "Optimistic: real results likely worse."
PAPER_NOTICE = "Paper trading only. No real money."

# Figures copied from V1_FREEZE_REPORT.md section 1 (2-year walk-forward, net of 0.2% per trade).
V1_BACKTESTS: List[Dict[str, Any]] = [
    {
        "period": "2007-2016",
        "strategy": {"cagr_pct": 1.09, "max_drawdown_pct": -20.7, "sharpe": 0.18},
        "spy_buy_hold": {"cagr_pct": 4.66, "max_drawdown_pct": -56.5, "sharpe": 0.32},
        "spy_above_200d": {"cagr_pct": 3.56, "max_drawdown_pct": -21.1, "sharpe": 0.37},
    },
    {
        "period": "2017-2026",
        "strategy": {"cagr_pct": 1.26, "max_drawdown_pct": -31.4, "sharpe": 0.19},
        "spy_buy_hold": {"cagr_pct": 13.40, "max_drawdown_pct": -34.1, "sharpe": 0.78},
        "spy_above_200d": {"cagr_pct": 7.83, "max_drawdown_pct": -25.1, "sharpe": 0.69},
    },
]

app = FastAPI(
    title="Paper Trader API",
    description="Read-only. " + PAPER_NOTICE,
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _clean(value: Any) -> Any:
    """Make a value JSON-safe: NaN/inf -> None, timestamps/dates -> ISO strings."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()[:10]
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):  # numpy scalar
        return _clean(value.item())
    return value


def _records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    return _clean(df.to_dict(orient="records"))


def _safe(name: str, fn: Callable[[], Any]) -> Any:
    """Run a reader; on failure log and return 503 with the reason (fail loud)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - surfaced to the client, never swallowed
        logger.error("API reader %s failed: %s", name, exc)
        raise HTTPException(status_code=503, detail=f"{name} unavailable: {exc}") from exc


@app.get("/api/status")
def status() -> Dict[str, Any]:
    return {
        "ok": True,
        "paper_only": True,
        "notice": PAPER_NOTICE,
        "initial_capital": settings.initial_capital,
        "benchmark": settings.get_benchmark("US"),
        "rules": {
            "buy_bar": settings.buy_bar,
            "signal_exit": settings.signal_exit,
            "stop_loss": settings.stop_loss,
            "take_profit": settings.take_profit,
            "max_positions": settings.max_positions,
        },
    }


@app.get("/api/overview")
def overview() -> Dict[str, Any]:
    def build() -> Dict[str, Any]:
        summary = dl.get_portfolio_summary("US")
        curve = dl.get_portfolio_vs_spy_chart_data("US")
        initial = float(settings.initial_capital)
        equity = float(summary["total_equity"])
        spy_last = float(curve["SPY Benchmark"].iloc[-1]) if not curve.empty else initial
        return _clean({
            "summary": summary,
            "initial_capital": initial,
            "return_pct": round((equity / initial - 1.0) * 100.0, 2) if initial > 0 else 0.0,
            "spy_return_pct": round((spy_last / initial - 1.0) * 100.0, 2) if initial > 0 else 0.0,
            "curve": _records(curve[["date", "My Portfolio", "SPY Benchmark"]]) if not curve.empty else [],
            "metrics": dl.get_performance_metrics_data("US"),
            "label": OPTIMISTIC_LABEL,
        })

    return _safe("overview", build)


@app.get("/api/portfolio")
def portfolio() -> Dict[str, Any]:
    def build() -> Dict[str, Any]:
        summary = dl.get_portfolio_summary("US")
        return _clean({
            "summary": summary,
            "stop_loss_pct": settings.stop_loss,
            "take_profit_pct": settings.take_profit,
            "sectors": dl.get_portfolio_sectors_summary("US"),
        })

    return _safe("portfolio", build)


@app.get("/api/trades")
def trades(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    return _safe("trades", lambda: {
        "trades": _records(dl.get_recent_trades_df(limit=limit, market="US")),
        "cost_per_trade_pct": 0.2,
    })


@app.get("/api/signals")
def signals() -> Dict[str, Any]:
    def build() -> Dict[str, Any]:
        regime, preds = dl.get_market_regime_and_predictions("US")
        return _clean({
            "regime": regime,
            "buy_bar": settings.buy_bar,
            "signal_exit": settings.signal_exit,
            "predictions": _records(preds),
        })

    return _safe("signals", build)


@app.get("/api/backtests")
def backtests() -> Dict[str, Any]:
    return {
        "source": "V1_FREEZE_REPORT.md",
        "label": OPTIMISTIC_LABEL,
        "net_of_cost_pct_per_trade": 0.2,
        "periods": V1_BACKTESTS,
        "note": "The strategy trails SPY buy-and-hold in both periods. Forward paper trading exists to measure, not to prove.",
    }


def _model_hash_status() -> Dict[str, Any]:
    path = Path(settings.data_models_dir) / "active_model.joblib"
    expected = settings.frozen_model_sha256
    if not path.exists():
        return {"file_found": False, "matches_freeze": False, "frozen": settings.model_freeze_enabled}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "file_found": True,
        "matches_freeze": digest == expected,
        "frozen": settings.model_freeze_enabled,
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return _safe("health", lambda: _clean({
        "pipeline": dl.get_last_pipeline_status(),
        "model": _model_hash_status(),
        "drift": dl.get_model_drift_summary(),
        "psi_note": "PSI drift protection is not active in V1 (see V1_FREEZE_REPORT.md).",
    }))
