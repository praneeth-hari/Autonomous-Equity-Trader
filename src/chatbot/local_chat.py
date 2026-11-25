"""
src/chatbot/local_chat.py — Section 10 Option C: AI Chatbot Engine (local LLM).

Gathers live system context and sends it to a model running locally in Ollama
(Llama 3.1 8B) to answer questions about portfolio performance, risk rules and
trading decisions. Nothing leaves this machine: the Ollama URL must be a local
address, so portfolio data is never sent to an outside service.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from config.settings import settings
from src.services.data_loader import (
    get_market_regime_and_predictions,
    get_portfolio_summary,
    get_recent_trades_df,
)
from src.db import repository
from src.llm import ollama_client
from src.llm.ollama_client import OllamaError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are a friendly AI assistant for an automated paper stock trading system.
You help the user understand their portfolio, trades, and system decisions in plain English.
Be friendly, casual and concise.
Always explain things in simple terms as if talking to someone who has never invested before. Never use financial jargon without immediately explaining what it means in brackets.

Examples of good responses:
- Instead of 'RSI is overbought at 74' say 'The stock has been rising very fast lately (score: 74/100)'
- Instead of 'MACD crossover detected' say 'The trend direction just changed which could mean the stock is about to move'
- Instead of 'portfolio drawdown -8%' say 'at its worst point your portfolio was down $800 from your starting $10,000'

Always end responses with:
Remember: This is paper trading with fake money — great for learning with zero risk! 🎓

Current Portfolio Data:
{portfolio_data}

Recent Trades:
{recent_trades}

Active Alerts:
{active_alerts}

Model Rankings Today:
{model_rankings}
"""

FRIENDLY_ERROR_MSG = (
    "Sorry, I can't reach the local AI model. Make sure Ollama is running and the model "
    "is downloaded, then try again."
)



def build_live_context_strings(market: str = "US") -> Dict[str, str]:
    """
    Gathers live context from the portfolio, trades, risk engine, and ML model.
    """
    curr_sym = settings.get_currency_symbol(market)
    # 1. Portfolio Data
    try:
        port = get_portfolio_summary(market=market)
        pos_str_list = []
        for p in port.get("positions", []):
            pos_str_list.append(
                f"- {p['ticker']}: {p['shares']:.2f} shares @ {curr_sym}{p['entry_price']:.2f} "
                f"(Current: {curr_sym}{p['current_price']:.2f}, PnL: {curr_sym}{p['unrealized_pnl']:+.2f})"
            )
        pos_str = "\n".join(pos_str_list) if pos_str_list else "No open positions (100% Cash)."

        portfolio_data = (
            f"Total Equity: {curr_sym}{port.get('total_equity', 10000.0):,.2f}\n"
            f"Cash: {curr_sym}{port.get('cash', 10000.0):,.2f} ({port.get('cash_reserve_pct', 100.0):.1f}%)\n"
            f"Open Positions Count: {port.get('open_positions_count', 0)} / {port.get('max_positions', 3)}\n"
            f"Open Positions:\n{pos_str}"
        )
    except Exception as e:
        logger.warning("Error gathering portfolio context: %s", e)
        portfolio_data = f"Portfolio Equity: {curr_sym}10,000.00, Cash: {curr_sym}10,000.00"

    # 2. Recent Trades
    try:
        trades_df = get_recent_trades_df(limit=10, market=market)
        if not trades_df.empty:
            tr_lines = []
            for _, r in trades_df.iterrows():
                tr_lines.append(
                    f"- {r.get('date')}: {r.get('action')} {r.get('shares')} {r.get('ticker')} @ "
                    f"{curr_sym}{r.get('price'):.2f} (Net PnL: {curr_sym}{r.get('net_pnl'):+.2f})"
                )
            recent_trades = "\n".join(tr_lines)
        else:
            recent_trades = "No recent trades recorded."
    except Exception as e:
        logger.warning("Error gathering trades context: %s", e)
        recent_trades = "No recent trades available."

    # 3. Active Alerts
    try:
        events = repository.get_events(limit=20)
        alert_lines = []
        for ev in events:
            if ev.get("level") in ("WARNING", "ERROR", "CRITICAL"):
                alert_lines.append(f"- [{ev.get('level')}] {ev.get('component')}: {ev.get('message')}")
        active_alerts = "\n".join(alert_lines) if alert_lines else "All systems operating normally. No active risk alerts."
    except Exception as e:
        logger.warning("Error gathering alerts context: %s", e)
        active_alerts = "No active risk alerts."

    # 4. Model Rankings Today
    try:
        regime, preds_df = get_market_regime_and_predictions(market=market)
        regime_status = "Risk-ON" if regime.get("is_risk_on") else "Risk-OFF (SPY < 200d MA)"
        if not preds_df.empty:
            rank_lines = [f"Regime: {regime_status}"]
            for rank_idx, (_, r) in enumerate(preds_df.head(5).iterrows()):
                prob_val = r.get("probability", 0.5)
                prob_str = f"{prob_val:.1%}" if isinstance(prob_val, (int, float)) else str(prob_val)
                rank_lines.append(
                    f"- #{rank_idx + 1} {r.get('ticker', '')} ({r.get('sector', '')}): Prob={prob_str}, "
                    f"Action={r.get('action_signal', 'HOLD')}, Sentiment={r.get('sentiment', '—')}"
                )
            model_rankings = "\n".join(rank_lines)
        else:
            model_rankings = f"Regime: {regime_status} — No candidate predictions available."
    except Exception as e:
        logger.warning("Error gathering model predictions context: %s", e)
        model_rankings = "Model: HistGradientBoostingActive, Regime: Normal."

    return {
        "portfolio_data": portfolio_data,
        "recent_trades": recent_trades,
        "active_alerts": active_alerts,
        "model_rankings": model_rankings,
    }


def generate_system_prompt(market: str = "US") -> str:
    """
    Builds the complete System Prompt with live data injected.
    """
    ctx = build_live_context_strings(market=market)
    return SYSTEM_PROMPT_TEMPLATE.format(
        portfolio_data=ctx["portfolio_data"],
        recent_trades=ctx["recent_trades"],
        active_alerts=ctx["active_alerts"],
        model_rankings=ctx["model_rankings"],
    )


def ask_local_chatbot(
    user_message: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    market: str = "US",
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> str:
    """
    Sends the user message with live context to the local Ollama server.
    Returns the reply text, or a friendly error message on any failure (details go to the log).
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": generate_system_prompt(market=market)}]
    for msg in (chat_history or [])[-6:]:  # keep the last 3 turns
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": str(msg.get("content", ""))})
    messages.append({"role": "user", "content": user_message})

    try:
        return ollama_client.chat(messages, base_url=base_url, model=model_name)
    except OllamaError as exc:
        logger.error("Chatbot could not get a local-model reply: %s", exc)
        return FRIENDLY_ERROR_MSG

