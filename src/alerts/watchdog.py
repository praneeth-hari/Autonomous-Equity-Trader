"""
src/alerts/watchdog.py — Alerts for things that go wrong AROUND the pipeline.

The pipeline can only report its own failures once Python has loaded. A broken environment,
a crash before the first line runs, or a PC that was off all night never reach it, which is how
the nightly run once failed for three weeks without a word. The nightly batch file, the missed-run
check and the health check call this module instead, so a failure is pushed to you.

  python -m src.alerts.watchdog run    --exit-code 1 --log logs/daily_run_2026-11-25.log
  python -m src.alerts.watchdog missed --expected 2026-11-24 --last 2026-11-20
  python -m src.alerts.watchdog env    --log logs/daily_run_2026-11-25.log   (or --problem "...")
  python -m src.alerts.watchdog backup --problem "Integrity check failed"
  python -m src.alerts.watchdog health --status CRITICAL --alert "Latest run failed"
  python -m src.alerts.watchdog test

Rules (see the project rules): alerts never contain secrets, each alert is sent at most once per
day and kind, and sending problems are logged, never raised into the run.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Exit codes written by src/pipeline/scheduler.py (and mirrored in run_trader.bat).
EXIT_OK, EXIT_DEGRADED, EXIT_HALTED = 0, 2, 3

_SECRET_PATTERNS = [
    re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}"),                      # Telegram bot token inside a URL
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),                     # bare Telegram token
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),                        # Google API key
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|apikey)\b\s*[=:]\s*\S+"),
    re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://)([^:\s/@]+):([^@\s/]+)@"),  # DB URL with password
]


def redact(text: str) -> str:
    """Remove anything that looks like a secret before text leaves the machine."""
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 3:
            out = pat.sub(r"\1\2:***@", out)
        else:
            out = pat.sub("***REDACTED***", out)
    return out


def tail_of_log(log_path: Optional[str], lines: int = 6) -> str:
    """The last few meaningful lines of a run log, redacted, for context in the alert."""
    if not log_path:
        return ""
    try:
        raw = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    keep = [ln.strip() for ln in raw if ln.strip() and "VALIDATION WARNING" not in ln]
    return redact("\n".join(keep[-lines:]))[:900]


_STATE = {"error": None}  # set when sending itself broke (for example a missing package), so the CLI can say so


def _send(message: str, key: str, notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    """Send once per key. Never raises."""
    _STATE["error"] = None
    try:
        if notify_fn is None:
            from src.alerts.telegram_alerts import notify as notify_fn  # imported late: needs the full environment
        return bool(notify_fn(redact(message), alert_key=key))
    except Exception as exc:  # noqa: BLE001 - an alert problem must not break the run it reports on
        _STATE["error"] = repr(exc)
        logger.error("WATCHDOG_ALERT_FAILED %s: %s", key, exc)
        return False


def failures_from_log(log_path: Optional[str]) -> List[str]:
    """The '[FAIL] ...' lines the pre-flight check wrote into a run log, redacted."""
    if not log_path:
        return []
    try:
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [redact(ln.split("[FAIL]", 1)[1].strip()) for ln in lines if "[FAIL]" in ln][-8:]


def alert_run_outcome(exit_code: int, log_path: Optional[str] = None, run_date: Optional[str] = None,
                      notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    """Alert for a nightly run that crashed (any code except 0 and 2) or was halted (3).

    0 is success and 2 is DEGRADED (some stocks skipped by the data check), which happens on most
    runs, so neither raises an alert; the daily summary already covers them.
    """
    if exit_code in (EXIT_OK, EXIT_DEGRADED):
        return False
    day = run_date or date.today().isoformat()
    if exit_code == EXIT_HALTED:
        head = "🛑 NIGHTLY RUN HALTED"
        why = "The kill switch is on, or another run was already in progress. No trading happened."
    else:
        head = "🚨 NIGHTLY RUN FAILED"
        why = f"It exited with code {exit_code}. No trading happened and your stop-losses were NOT checked."
    parts = [head, f"📅 {day}", why]
    tail = tail_of_log(log_path)
    if tail:
        parts += ["", "Last log lines:", tail]
    parts += ["", "Action: open logs/daily_run_" + day + ".log, fix the cause, then run run_trader.bat."]
    return _send("\n".join(parts), f"WATCHDOG_RUN_{exit_code}_{day}", notify_fn)


def alert_missed_run(expected: str, last: Optional[str], notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    msg = "\n".join([
        "⏰ MISSED NIGHTLY RUN",
        f"Expected a run for {expected}; the last one on record is {last or 'none'}.",
        "The PC was probably off or asleep. Open positions were not checked against their stops.",
        "Action: start the PC and run run_trader.bat.",
    ])
    return _send(msg, f"WATCHDOG_MISSED_{expected}", notify_fn)


def alert_environment_problem(problems: List[str], day: Optional[str] = None,
                              notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    day = day or date.today().isoformat()
    msg = "\n".join(["🧰 ENVIRONMENT CHECK FAILED", f"📅 {day}", "The nightly run was not started:"]
                    + [f"- {p}" for p in problems[:8]]
                    + ["", "Action: run  .venv\\Scripts\\python.exe -m pip install -r requirements.txt"])
    return _send(msg, f"WATCHDOG_ENV_{day}", notify_fn)


def alert_backup_problem(problem: str, day: Optional[str] = None,
                         notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    day = day or date.today().isoformat()
    msg = "\n".join(["💾 BACKUP FAILED", f"📅 {day}", problem[:400],
                     "The nightly run still went ahead, but there is no fresh restore point.",
                     "Action: run  python -m src.ops.backup create  and read the message."])
    return _send(msg, f"WATCHDOG_BACKUP_{day}", notify_fn)


def alert_health(status: str, alerts: List[str], day: Optional[str] = None,
                 notify_fn: Optional[Callable[..., bool]] = None) -> bool:
    """Alert from the morning health check. Only CRITICAL, or a WARNING that mentions a missed run."""
    status = status.upper()
    missed = any("expected" in a.lower() or "missed" in a.lower() for a in alerts)
    if status != "CRITICAL" and not (status == "WARNING" and missed):
        return False
    day = day or date.today().isoformat()
    icon = "🚨" if status == "CRITICAL" else "⚠️"
    msg = "\n".join([f"{icon} HEALTH CHECK {status}", f"📅 {day}"] + [f"- {a}" for a in alerts[:6]])
    return _send(msg, f"WATCHDOG_HEALTH_{status}_{day}", notify_fn)


def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Send a watchdog alert.")
    sub = p.add_subparsers(dest="kind", required=True)
    r = sub.add_parser("run"); r.add_argument("--exit-code", type=int, required=True); r.add_argument("--log"); r.add_argument("--date")
    m = sub.add_parser("missed"); m.add_argument("--expected", required=True); m.add_argument("--last")
    e = sub.add_parser("env"); e.add_argument("--problem", action="append", default=[]); e.add_argument("--log")
    b = sub.add_parser("backup"); b.add_argument("--problem", required=True)
    h = sub.add_parser("health"); h.add_argument("--status", required=True); h.add_argument("--alert", action="append", default=[])
    sub.add_parser("test")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    _STATE["error"] = None  # a command that sends nothing must not inherit an earlier failure

    if a.kind == "run":
        sent = alert_run_outcome(a.exit_code, a.log, a.date)
    elif a.kind == "missed":
        sent = alert_missed_run(a.expected, a.last)
    elif a.kind == "env":
        problems = list(a.problem) + failures_from_log(a.log)
        sent = alert_environment_problem(problems or ["The environment check failed. See the run log."])
    elif a.kind == "backup":
        sent = alert_backup_problem(a.problem)
    elif a.kind == "health":
        sent = alert_health(a.status, a.alert)
    else:
        sent = _send("✅ Watchdog test: alerts reach you.", f"WATCHDOG_TEST_{date.today().isoformat()}")
    if _STATE["error"]:
        print("ALERT COULD NOT BE SENT: " + redact(str(_STATE["error"])))
        return 1  # the batch file then retries with the system Python
    print("alert sent" if sent else "no alert sent (not needed, duplicate, or Telegram not configured)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
