"""
src/api/app.py — Read-only FastAPI layer for the new frontend.

Project rules:
  * Read-only: every endpoint reads. The single POST, /api/chat, only asks the local LLM a question
    (it changes no state). No trading, no broker, no model promotion.
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
from pydantic import BaseModel, Field

from config.settings import settings
from src.chatbot.local_chat import FRIENDLY_ERROR_MSG, ask_local_chatbot
from src.llm import ollama_client
from src.services import data_loader as dl
from src.services import market_service as ms

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
    allow_methods=["GET", "POST"],
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


MIN_DAYS_FOR_RATIOS = 30  # project rule: flag small samples (N < 30); ratios on a few days are noise


@app.get("/api/performance")
def performance() -> Dict[str, Any]:
    def build() -> Dict[str, Any]:
        equity = dl.get_equity_history_df("US")
        days = int(len(equity))
        closed, summary, _export = dl.get_closed_trade_history("US")
        closed_rows = [
            {
                "date_bought": r["Date Bought"], "date_sold": r["Date Sold"], "ticker": r["Ticker"],
                "entry_price": r["Entry Price"], "exit_price": r["Exit Price"], "shares": r["Shares"],
                "pnl": r["Profit / Loss ($)"], "pnl_pct": r["Profit / Loss (%)"], "exit_reason": r["Exit Reason"],
                "model_score": r["Model Score at Entry"],
            }
            for r in _records(closed)
        ]
        return _clean({
            "sample_days": days,
            "enough_history": days >= MIN_DAYS_FOR_RATIOS,
            "min_days": MIN_DAYS_FOR_RATIOS,
            "metrics": dl.get_performance_metrics_data("US"),
            "drawdown": _records(dl.get_drawdown_series("US")),
            "daily_returns": _records(dl.get_daily_returns_histogram_data(15, "US")),
            "win_loss": _records(dl.get_win_loss_trades_chart_data(200, "US")),
            "sectors": _records(dl.get_sector_allocation_donut_data("US")),
            "closed_summary": summary,
            "closed_trades": closed_rows,
            "label": OPTIMISTIC_LABEL,
        })

    return _safe("performance", build)


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


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: List[ChatTurn] = Field(default_factory=list, max_length=12)


@app.get("/api/chat/status")
def chat_status() -> Dict[str, Any]:
    """Is the local model server reachable? (The model itself loads on the first question.)"""
    return {"available": ollama_client.is_available(), "model": settings.ollama_model, "local_only": True}


@app.post("/api/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """Ask the local Ollama model about the portfolio. Reads state only; never trades."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty.")
    history = [{"role": t.role, "content": t.content} for t in req.history]
    reply = ask_local_chatbot(message, chat_history=history, market="US")
    return {"reply": reply, "ok": reply != FRIENDLY_ERROR_MSG}


# ── Market data (Yahoo Finance via the local service; read-only display) ──────

def _market(name: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ms.InvalidSymbol as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ms.MarketDataError as exc:
        logger.error("Market reader %s failed: %s", name, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/market/overview")
def market_overview() -> Dict[str, Any]:
    return _market("market overview", lambda: _clean(ms.get_overview()))


@app.get("/api/market/quotes")
def market_quotes(symbols: str = Query(..., min_length=1, max_length=400)) -> Dict[str, Any]:
    wanted = [s for s in symbols.split(",") if s.strip()]
    if not 1 <= len(wanted) <= 40:
        raise HTTPException(status_code=422, detail="Ask for between 1 and 40 symbols.")
    return _market("market quotes", lambda: {"quotes": _clean(ms.get_quotes(wanted))})


@app.get("/api/market/history/{symbol}")
def market_history(
    symbol: str,
    interval: str = Query("1day"),
    bars: int = Query(120, ge=20, le=500),
    spy: bool = Query(False),
) -> Dict[str, Any]:
    return _market("market history", lambda: _clean(ms.get_history(symbol, interval, bars, with_spy=spy)))


@app.get("/api/market/stock/{symbol}")
def market_stock(symbol: str) -> Dict[str, Any]:
    return _market("market stock", lambda: _clean(ms.get_stock(symbol)))
