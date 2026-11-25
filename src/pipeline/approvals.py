"""
src/pipeline/approvals.py — Optional human approval for new buys (paper trading only).

OFF by default (HUMAN_APPROVAL_REQUIRED=false), so the frozen V1 behaviour is unchanged. When ON:

  * A BUY queued by one run fills at the next run only if you approved it in the dashboard.
    No decision means no buy: doing nothing is the capital-preserving default.
  * A SELL is never held back. Approval gates NEW risk, never the removal of risk: a stop-loss
    that waited for a human could leave a loss running while you are away.
  * The risk engine still sits in front of every order. Approval cannot add a trade the risk engine
    vetoed, because only orders the engine and allocator already produced can ever be approved.

Decisions live in data/approvals_<market>.json next to the pending-orders file. A damaged or missing
file means "no approvals", never "everything approved".
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

APPROVED, REJECTED = "APPROVED", "REJECTED"
KEEP_DAYS = 30


def _get(order: Any, key: str) -> Any:
    return order[key] if isinstance(order, dict) else getattr(order, key)


def order_id(order: Any) -> str:
    """Stable id of a queued order: the day it was generated, the side and the ticker."""
    return f"{_get(order, 'date')}:{str(_get(order, 'action')).upper()}:{str(_get(order, 'ticker')).upper()}"


def requires_approval(order: Any) -> bool:
    return str(_get(order, "action")).upper() == "BUY"


def _path(market: str) -> Path:
    from src.trading import paper_broker  # read at call time: tests redirect this directory

    return Path(paper_broker.PENDING_ORDERS_DIR) / f"approvals_{market.lower()}.json"


def load_decisions(market: str = "US") -> Dict[str, Dict[str, str]]:
    p = _path(market)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        decisions = data.get("decisions", {})
        return {k: v for k, v in decisions.items() if isinstance(v, dict) and v.get("status") in (APPROVED, REJECTED)}
    except Exception as exc:  # noqa: BLE001 - fail safe: an unreadable file approves nothing
        logger.error("APPROVALS_FILE_UNREADABLE %s: %s (treating every buy as not approved)", p, exc)
        return {}


def _write(market: str, decisions: Dict[str, Dict[str, str]]) -> None:
    p = _path(market)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"decisions": decisions}, indent=2), encoding="utf-8")
    os.replace(tmp, p)  # atomic: a crash never leaves a half-written file


def record_decision(market: str, oid: str, status: str, note: str = "") -> Dict[str, str]:
    if status not in (APPROVED, REJECTED):
        raise ValueError(f"Unknown decision '{status}'.")
    decisions = load_decisions(market)
    decisions[oid] = {"status": status, "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": note[:200]}
    _write(market, decisions)
    return decisions[oid]


def prune(market: str, now: datetime = None) -> int:
    """Forget decisions older than KEEP_DAYS so the file does not grow forever."""
    now = now or datetime.now(timezone.utc)
    decisions = load_decisions(market)
    keep = {}
    for k, v in decisions.items():
        try:
            if now - datetime.fromisoformat(v["decided_at"]) <= timedelta(days=KEEP_DAYS):
                keep[k] = v
        except (KeyError, ValueError):
            continue
    if len(keep) != len(decisions):
        _write(market, keep)
    return len(decisions) - len(keep)


def pending_view(orders: List[Any], market: str = "US") -> List[Dict[str, Any]]:
    """Queued orders as the dashboard shows them, each with its approval status."""
    decisions = load_decisions(market)
    out = []
    for o in orders:
        oid = order_id(o)
        need = requires_approval(o)
        status = "AUTO" if not need else decisions.get(oid, {}).get("status", "PENDING")
        out.append({
            "id": oid, "date": str(_get(o, "date")), "ticker": str(_get(o, "ticker")), "action": str(_get(o, "action")).upper(),
            "shares": float(_get(o, "shares")), "price": float(_get(o, "reference_price")), "value": float(_get(o, "gross_value")),
            "reason": str(_get(o, "reason")), "requires_approval": need, "status": status,
        })
    return out


def filter_for_fill(orders: List[Any], market: str = "US") -> Tuple[List[Any], List[Tuple[Any, str]]]:
    """Split queued orders into (may fill, dropped with the reason). A no-op when approval mode is off."""
    if not settings.human_approval_required:
        return list(orders), []
    decisions = load_decisions(market)
    keep, dropped = [], []
    for o in orders:
        if not requires_approval(o):
            keep.append(o)
            continue
        status = decisions.get(order_id(o), {}).get("status")
        if status == APPROVED:
            keep.append(o)
        elif status == REJECTED:
            dropped.append((o, "you rejected it"))
        else:
            dropped.append((o, "no approval was given before the run"))
    return keep, dropped


def announce_pending(orders: List[Any], run_date: str) -> bool:
    """Tell you (Telegram) that buys are waiting. Never raises; a missing alert just means check the dashboard."""
    if not settings.human_approval_required:
        return False
    buys = [o for o in orders if requires_approval(o)]
    if not buys:
        return False
    try:
        from src.alerts.telegram_alerts import notify

        lines = ["📝 APPROVAL NEEDED", f"📅 {run_date}", f"{len(buys)} buy order(s) are waiting:"]
        lines += [f"- {_get(o, 'ticker')}: {float(_get(o, 'shares')):.2f} shares, about ${float(_get(o, 'gross_value')):,.0f}" for o in buys[:8]]
        lines += ["", "Open the Approvals page before the next run. No approval means no buy."]
        return bool(notify("\n".join(lines), alert_key=f"APPROVAL_NEEDED_{run_date}"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("APPROVAL_ANNOUNCE_FAILED: %s", exc)
        return False
