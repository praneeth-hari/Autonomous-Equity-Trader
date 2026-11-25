"""
src/services/market_service.py — Market data for the Markets / Stock / Watchlist pages.

Source: Yahoo Finance via yfinance (already a project dependency). Only ticker symbols leave this
machine; no portfolio data is ever sent.

Project rules:
  * Fail loud: network problems or empty data raise MarketDataError; nothing is invented or filled.
  * Symbols are validated before use.
  * This module never touches the trading database or the broker; it is read-only market display.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from config.settings import settings

logger = logging.getLogger(__name__)

ETFS: List[Tuple[str, str]] = [
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF"),
    ("IWM", "iShares Russell 2000 ETF"),
]

NAMES: Dict[str, str] = {
    **dict(ETFS),
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "NVDA": "NVIDIA Corporation",
    "GOOGL": "Alphabet Inc.", "META": "Meta Platforms, Inc.", "VZ": "Verizon Communications Inc.",
    "CMCSA": "Comcast Corporation", "AMZN": "Amazon.com, Inc.", "TSLA": "Tesla, Inc.",
    "HD": "The Home Depot, Inc.", "JPM": "JPMorgan Chase & Co.", "V": "Visa Inc.",
    "BAC": "Bank of America Corporation", "UNH": "UnitedHealth Group Incorporated",
    "JNJ": "Johnson & Johnson", "LLY": "Eli Lilly and Company", "CAT": "Caterpillar Inc.",
    "GE": "GE Aerospace", "UPS": "United Parcel Service, Inc.", "PG": "The Procter & Gamble Company",
    "COST": "Costco Wholesale Corporation", "KO": "The Coca-Cola Company",
    "XOM": "Exxon Mobil Corporation", "CVX": "Chevron Corporation", "COP": "ConocoPhillips",
}

# UI interval -> (yfinance interval, yfinance period, resample rule or None)
INTERVALS: Dict[str, Tuple[str, str, Optional[str]]] = {
    "5min": ("5m", "5d", None),
    "15min": ("15m", "5d", None),
    "30min": ("30m", "1mo", None),
    "1h": ("60m", "3mo", None),
    "4h": ("60m", "6mo", "4h"),
    "1day": ("1d", "1y", None),
    "1week": ("1wk", "5y", None),
    "1month": ("1mo", "max", None),
}

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_CACHE: Dict[Any, Tuple[float, Any]] = {}
_LOCK = threading.Lock()


class MarketDataError(RuntimeError):
    """Market data could not be fetched or was empty (network down, unknown symbol, ...)."""


class InvalidSymbol(ValueError):
    """The ticker symbol is not a plausible symbol."""


def normalize_symbol(raw: str) -> str:
    sym = str(raw or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise InvalidSymbol(f"'{raw}' is not a valid ticker symbol.")
    return sym


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def _cached(key: Any, ttl: float, fn: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def _download(symbols: List[str], period: str, interval: str) -> pd.DataFrame:
    """One batched Yahoo request. Isolated so tests can replace it."""
    try:
        return yf.download(
            tickers=symbols, period=period, interval=interval, group_by="ticker",
            auto_adjust=True, progress=False, threads=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f"Could not reach Yahoo Finance: {exc}") from exc


def _frame_for(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pull one symbol's OHLCV out of a yfinance frame, whatever the column layout."""
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        lv0 = set(df.columns.get_level_values(0))
        part = df[symbol] if symbol in lv0 else df.xs(symbol, axis=1, level=1) if symbol in set(df.columns.get_level_values(1)) else pd.DataFrame()
    else:
        part = df
    if part.empty:
        return pd.DataFrame()
    part = part.rename(columns=str.title)
    need = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in part.columns for c in need):
        return pd.DataFrame()
    return part[need].dropna(subset=["Close"])


def _epoch(ts: Any) -> int:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp())


def _quote_from(frame: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    if len(frame) < 2:
        raise MarketDataError(f"Not enough price history for {symbol}.")
    last, prev = frame.iloc[-1], frame.iloc[-2]
    change = float(last["Close"] - prev["Close"])
    return {
        "symbol": symbol,
        "name": NAMES.get(symbol, symbol),
        "price": round(float(last["Close"]), 4),
        "prev_close": round(float(prev["Close"]), 4),
        "change": round(change, 4),
        "change_pct": round(change / float(prev["Close"]) * 100.0, 3) if prev["Close"] else 0.0,
        "volume": int(last["Volume"]) if pd.notna(last["Volume"]) else 0,
        "spark": [round(float(v), 4) for v in frame["Close"].tail(30)],
        "in_universe": symbol in set(settings.get_universe("US")),
    }


def get_quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    """Latest daily quote and a 30-bar sparkline for each symbol. Unknown symbols are skipped and logged."""
    syms = sorted({normalize_symbol(s) for s in symbols})
    if not syms:
        return []

    def fetch() -> List[Dict[str, Any]]:
        df = _download(syms, "3mo", "1d")
        out, missing = [], []
        for s in syms:
            frame = _frame_for(df, s)
            try:
                out.append(_quote_from(frame, s))
            except MarketDataError:
                missing.append(s)
        if missing:
            logger.warning("MARKET_NO_DATA: no usable prices for %s", ", ".join(missing))
        if not out:
            raise MarketDataError("No price data came back. Check your internet connection or the symbols.")
        for q in out:  # the model's latest STORED score, for the 25 universe stocks only
            q["model"] = _model_score(q["symbol"]) if q["in_universe"] else None
        return out

    return _cached(("quotes", tuple(syms)), 300, fetch)


def get_overview() -> Dict[str, Any]:
    """Index ETFs, the 25-stock universe with movers, and heatmap weights (price x volume)."""
    etf_syms = [s for s, _ in ETFS]
    universe = list(settings.get_universe("US"))
    quotes = {q["symbol"]: q for q in get_quotes(etf_syms + universe)}
    etfs = [quotes[s] for s in etf_syms if s in quotes]
    stocks = [quotes[s] for s in universe if s in quotes]
    for q in stocks:
        q["weight"] = round(q["price"] * q["volume"], 2)
    movers = sorted(stocks, key=lambda q: abs(q["change_pct"]), reverse=True)
    return {"etfs": etfs, "movers": movers[:5], "universe": stocks}


def _resample_4h(frame: pd.DataFrame) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return frame.resample("4h").agg(agg).dropna(subset=["Close"])


def _bars(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    return [
        {"t": _epoch(ts), "o": round(float(r.Open), 4), "h": round(float(r.High), 4),
         "l": round(float(r.Low), 4), "c": round(float(r.Close), 4), "v": int(r.Volume) if pd.notna(r.Volume) else 0}
        for ts, r in frame.iterrows()
    ]


def get_history(symbol: str, interval: str = "1day", bars: int = 120, with_spy: bool = False) -> Dict[str, Any]:
    sym = normalize_symbol(symbol)
    if interval not in INTERVALS:
        raise InvalidSymbol(f"Unknown interval '{interval}'.")
    yf_interval, period, resample = INTERVALS[interval]
    bars = max(20, min(int(bars), 500))
    ttl = 60 if yf_interval.endswith("m") and yf_interval != "1mo" else 300

    def one(s: str) -> pd.DataFrame:
        def fetch() -> pd.DataFrame:
            frame = _frame_for(_download([s], period, yf_interval), s)
            if frame.empty:
                raise MarketDataError(f"No {interval} prices for {s}. The symbol may be wrong or the market data unavailable.")
            return _resample_4h(frame) if resample else frame

        return _cached(("hist", s, interval), ttl, fetch)

    frame = one(sym).tail(bars)
    result: Dict[str, Any] = {"symbol": sym, "name": NAMES.get(sym, sym), "interval": interval, "bars": _bars(frame)}
    if with_spy and sym != "SPY":
        spy = one("SPY")
        spy = spy[spy.index.isin(frame.index)]
        result["spy"] = [{"t": _epoch(ts), "c": round(float(c), 4)} for ts, c in spy["Close"].items()]
    return result


def _stock_name(sym: str) -> str:
    if sym in NAMES:
        return NAMES[sym]
    try:
        info = yf.Ticker(sym).get_info()
        return str(info.get("shortName") or info.get("longName") or sym)
    except Exception:  # noqa: BLE001 - the symbol is a fine fallback label
        return sym


def get_stock(symbol: str) -> Dict[str, Any]:
    """Quote, key stats, the model's stored score (universe tickers only) and recent headlines."""
    sym = normalize_symbol(symbol)

    def fetch_quote() -> Dict[str, Any]:
        frame = _frame_for(_download([sym], "1y", "1d"), sym)
        if frame.empty:
            raise MarketDataError(f"No price data for {sym}. The symbol may be wrong or the market data unavailable.")
        q = _quote_from(frame, sym)
        q["name"] = _stock_name(sym)
        last = frame.iloc[-1]
        q.update({
            "open": round(float(last["Open"]), 4),
            "high": round(float(last["High"]), 4),
            "low": round(float(last["Low"]), 4),
            "week52_high": round(float(frame["High"].max()), 4),
            "week52_low": round(float(frame["Low"].min()), 4),
            "as_of": _epoch(frame.index[-1]),
        })
        return q

    stock = dict(_cached(("stock", sym), 300, fetch_quote))
    stock["model"] = _model_score(sym)
    stock["headlines"] = _headlines(sym)
    return stock


def _model_score(sym: str) -> Optional[Dict[str, Any]]:
    """The model's latest STORED prediction. None for tickers outside the universe or with no stored score."""
    if sym not in set(settings.get_universe("US")):
        return None
    try:
        from src.db import repository

        df = repository.get_predictions(sym)
        if df.empty:
            return None
        row = df.iloc[-1]
        p = float(row["probability"])
        zone = "buy zone" if p >= settings.buy_bar else "exit zone" if p < settings.signal_exit else "wait zone"
        return {"probability": round(p, 4), "date": str(row["date"])[:10], "zone": zone}
    except Exception as exc:  # noqa: BLE001
        logger.warning("MARKET_MODEL_SCORE_UNAVAILABLE for %s: %s", sym, exc)
        return None


def _headlines(sym: str) -> List[Dict[str, Any]]:
    try:
        from src.intelligence.sentiment import fetch_headlines_for_ticker, get_vader_sentiment

        out = []
        for h in fetch_headlines_for_ticker(sym, limit=5):
            compound = float(get_vader_sentiment(h).get("compound", 0.0))
            out.append({"title": h, "sentiment": "positive" if compound > 0.05 else "negative" if compound < -0.05 else "neutral"})
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("MARKET_HEADLINES_UNAVAILABLE for %s: %s", sym, exc)
        return []
