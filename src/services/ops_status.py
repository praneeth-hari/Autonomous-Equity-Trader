"""
src/services/ops_status.py — "Is the system healthy?" facts for the Health page.

Everything here is read-only and fails soft: a problem reading one fact becomes a clear
"unknown" for that fact, never an exception that blanks the whole page.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_MARKERS = [  # (text in the log line, outcome); the LAST marker in a run log decides its outcome
    ("[SUCCESS]", "SUCCESS"),
    ("[DEGRADED]", "DEGRADED"),
    ("[HALTED]", "HALTED"),
    ("PIPELINE FAILED", "FAILED"),
]
_LOG_RE = re.compile(r"^daily_run_(\d{4}-\d{2}-\d{2})\.log$")
_CACHE: Dict[str, Any] = {}


def _ttl(key: str, seconds: float, fn):
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < seconds:
        return hit[1]
    value = fn()
    _CACHE[key] = (now, value)
    return value


def clear_cache() -> None:
    _CACHE.clear()


def _outcome_of(log: Path) -> str:
    outcome = "UNKNOWN"
    try:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            for text, name in _MARKERS:
                if text in line:
                    outcome = name
    except OSError:
        return "UNKNOWN"
    return outcome


def run_history(logs_dir: Optional[Path] = None, today: Optional[date] = None, days: int = 14) -> List[Dict[str, str]]:
    """One entry per day in the last `days`, oldest first. A weekday with no log is MISSED; weekends are left out."""
    logs_dir = Path(logs_dir or ROOT / "logs")
    today = today or date.today()
    found = {m.group(1): p for p in (logs_dir.glob("daily_run_*.log") if logs_dir.exists() else []) if (m := _LOG_RE.match(p.name))}
    out: List[Dict[str, str]] = []
    for back in range(days - 1, -1, -1):
        d = today - timedelta(days=back)
        key = d.isoformat()
        if key in found:
            out.append({"date": key, "outcome": _outcome_of(found[key])})
        elif d.weekday() < 5 and d != today:  # today may simply not have run yet
            out.append({"date": key, "outcome": "MISSED"})
    return out


def backup_status(db_url: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    from src.ops import backup as bk

    try:
        live = bk.sqlite_path(db_url)
    except bk.BackupError as exc:
        return {"supported": False, "message": str(exc)}
    files = bk.list_backups(live)
    if not files:
        return {"supported": True, "count": 0, "message": "No backup yet. One is made before each nightly run."}
    newest = files[-1]
    stamp = bk.BACKUP_RE.match(newest.name)
    made = datetime.strptime(stamp.group(1) + stamp.group(2), "%Y%m%d%H%M%S")
    age_h = ((now or datetime.now()) - made).total_seconds() / 3600
    return {"supported": True, "count": len(files), "newest": newest.name, "age_hours": round(age_h, 1),
            "size_mb": round(newest.stat().st_size / 1e6, 1), "stale": age_h > 48}


def environment_status() -> Dict[str, Any]:
    """The pre-flight check, cached for ten minutes (it loads the model, so it is not free)."""
    from src.ops import envcheck

    def run() -> Dict[str, Any]:
        r = envcheck.run_checks()
        return {"ok": r.ok, "problems": r.problems, "warnings": r.warnings, "info": r.info}

    try:
        return _ttl("env", 600, run)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "problems": [f"The environment check could not run: {exc}"], "warnings": [], "info": []}


def skipped_tickers(limit: int = 60) -> Dict[str, Any]:
    """Stocks the data check rejected in the most recent run, with the reason."""
    from src.db import repository

    try:
        events = repository.get_events(component="daily_pipeline", limit=300)
    except Exception as exc:  # noqa: BLE001
        return {"date": None, "skipped": [], "message": f"Could not read events: {exc}"}
    skips = [e for e in events if str(e.get("message", "")).startswith("SKIP ")][:limit]
    if not skips:
        return {"date": None, "skipped": []}
    day = str(skips[0]["timestamp"])[:10]
    seen: Dict[str, str] = {}
    for e in skips:
        if str(e["timestamp"])[:10] != day:
            continue
        m = re.match(r"SKIP (\S+?):\s*(.*)", str(e["message"]))
        if m and m.group(1) not in seen:
            seen[m.group(1)] = m.group(2)[:200]
    return {"date": day, "skipped": [{"ticker": t, "reason": r} for t, r in sorted(seen.items())]}


def data_quality() -> Dict[str, Any]:
    """Stored price history audit (schema, staleness, holes), cached for ten minutes."""
    from src.ops import data_audit

    def run() -> Dict[str, Any]:
        tickers = list(settings.get_universe("US")) + [settings.get_benchmark("US")]
        results = data_audit.audit(tickers)
        return {"checked": len(results), "problems": [{"ticker": r.ticker, "issues": r.problems()} for r in results if not r.ok]}

    try:
        return _ttl("data_quality", 600, run)
    except Exception as exc:  # noqa: BLE001
        return {"checked": 0, "problems": [], "message": f"The data audit could not run: {exc}"}


def kill_switch_status() -> Dict[str, Any]:
    from src.db import repository

    try:
        enabled, reason = repository.load_kill_switch_state()
        return {"enabled": bool(enabled), "reason": reason or ""}
    except Exception as exc:  # noqa: BLE001
        return {"enabled": None, "reason": f"Could not read the kill switch: {exc}"}


def alerts_status() -> Dict[str, Any]:
    token = (getattr(settings, "telegram_bot_token", "") or "").strip()
    chat = (getattr(settings, "telegram_chat_id", "") or "").strip()
    from src.alerts import heartbeat

    # booleans only, never the values: the bot token and the ping URL are secrets
    return {"telegram_configured": bool(token and chat), "heartbeat_configured": heartbeat.configured()}


def summary() -> Dict[str, Any]:
    history = run_history()
    return {
        "run_history": history,
        "missed_days": [h["date"] for h in history if h["outcome"] == "MISSED"],
        "backups": backup_status(),
        "environment": environment_status(),
        "data_skips": skipped_tickers(),
        "data_quality": data_quality(),
        "kill_switch": kill_switch_status(),
        "alerts": alerts_status(),
    }
