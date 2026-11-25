"""
src/alerts/heartbeat.py — "Dead man's switch" pings for the nightly run (healthchecks.io or a self-hosted copy).

Why: every other alert is sent BY this computer, so none can fire when the computer is off, asleep or
crashed. A heartbeat flips it round: the run pings an outside service when it starts and when it ends,
and the SERVICE messages you when an expected ping does not arrive.

  python -m src.alerts.heartbeat start     # the run began
  python -m src.alerts.heartbeat ok        # the run finished (success or degraded)
  python -m src.alerts.heartbeat fail --message "exit code 1"

Setup (once, by you): create a free check at healthchecks.io, set its schedule to the weekday run time with a
generous grace period, choose how it should reach you, then put the check's ping URL in .env as
HEALTHCHECK_PING_URL. With no URL this module does nothing.

What leaves the machine: one short HTTPS request with a few words ("exit code 1"). No portfolio data.
The ping URL is treated like a secret (anyone holding it can send pings): it is never logged or shown.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from typing import List, Optional
from urllib.parse import urlparse

from config.settings import settings

logger = logging.getLogger(__name__)

SUFFIX = {"start": "/start", "ok": "", "fail": "/fail"}
_SAFE = re.compile(r"[^\w .,:;()=/+-]")


def clean_url(url: Optional[str]) -> Optional[str]:
    """A usable ping URL, or None. Only http(s) with a host; no embedded credentials."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return None
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    return raw


def ping(state: str, message: str = "", url: Optional[str] = None, timeout: float = 10.0) -> bool:
    """Send one ping. Returns True when the service accepted it. Never raises and never logs the URL."""
    if state not in SUFFIX:
        raise ValueError(f"Unknown heartbeat state '{state}'.")
    base = clean_url(url if url is not None else getattr(settings, "healthcheck_ping_url", ""))
    if base is None:
        return False
    try:
        import requests

        body = _SAFE.sub("", message)[:200]
        resp = requests.post(base + SUFFIX[state], data=body.encode("utf-8"), timeout=timeout)
        ok = resp.status_code < 300
        if not ok:
            logger.warning("HEARTBEAT_REJECTED state=%s status=%s", state, resp.status_code)
        return ok
    except Exception as exc:  # noqa: BLE001 - a heartbeat problem must never disturb the run
        logger.warning("HEARTBEAT_FAILED state=%s: %s", state, type(exc).__name__)  # type only: the message can contain the URL
        return False


def configured() -> bool:
    return clean_url(getattr(settings, "healthcheck_ping_url", "")) is not None


def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Send a heartbeat ping.")
    p.add_argument("state", choices=sorted(SUFFIX))
    p.add_argument("--message", default="")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not configured():
        print("Heartbeat not configured (HEALTHCHECK_PING_URL is empty): nothing sent.")
        return 0
    print(f"Heartbeat '{a.state}' " + ("sent." if ping(a.state, a.message) else "could not be sent."))
    return 0  # never fails the run


if __name__ == "__main__":
    sys.exit(_main())
