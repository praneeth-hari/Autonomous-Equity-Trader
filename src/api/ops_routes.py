"""
src/api/ops_routes.py — Approvals and the kill switch (the only routes that change anything).

What they can and cannot do:
  * They never place, size or price a trade. Approving only lets an order that the risk engine and
    allocator ALREADY produced fill at the next run; rejecting or ignoring it means it does not.
  * Only BUYs can be approved or rejected. SELLs always execute (they remove risk).
  * The kill switch halts the whole nightly run. While it is ON nothing runs at all: no buys, no sells,
    and stop-losses are not checked. The page says so.

Every state-changing request must come from the local web app: it needs the custom header
X-Requested-With: paper-trader (which a browser will not send cross-site without a CORS preflight, and
the CORS policy only allows the local dev origin) and, when an Origin header is present, it must be local.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config.settings import settings
from src.db import repository
from src.pipeline import approvals
from src.services import ops_status

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]  # Host header names this API answers to (port ignored)
UI_HEADER = ("x-requested-with", "paper-trader")
MARKET = "US"

router = APIRouter()


def require_local_ui(request: Request) -> None:
    if request.headers.get(UI_HEADER[0]) != UI_HEADER[1]:
        raise HTTPException(status_code=403, detail="This action can only be taken from the Paper Trader web app.")
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="This request came from an origin that is not allowed.")


def _pending_orders() -> list:
    snap = repository.get_latest_portfolio_snapshot(MARKET)
    return list(snap.get("pending_orders") or []) if snap else []


def _approvals_payload() -> Dict[str, Any]:
    snap = repository.get_latest_portfolio_snapshot(MARKET)
    return {
        "approval_required": bool(settings.human_approval_required),
        "run_date": snap["run_date"] if snap else None,
        "orders": approvals.pending_view(_pending_orders(), MARKET),
        "how_it_works": [
            "Buys wait here after each nightly run and fill at the next run only if you approve them.",
            "No decision means no buy.",
            "Sells (including stop-losses) are never held back, because they remove risk.",
        ],
        "enable_hint": "Set HUMAN_APPROVAL_REQUIRED=true in .env and restart to turn approval on." if not settings.human_approval_required else "",
    }


@router.get("/api/approvals")
def list_approvals() -> Dict[str, Any]:
    try:
        return _approvals_payload()
    except Exception as exc:  # noqa: BLE001
        logger.error("Approvals reader failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"approvals unavailable: {exc}") from exc


def _decide(order_id: str, status: str, request: Request) -> Dict[str, Any]:
    require_local_ui(request)
    if not settings.human_approval_required:
        raise HTTPException(status_code=409, detail="Approval mode is off, so orders fill automatically and a decision would change nothing.")
    match = next((o for o in approvals.pending_view(_pending_orders(), MARKET) if o["id"] == order_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="That order is not waiting for approval (it may already have been filled or dropped).")
    if not match["requires_approval"]:
        raise HTTPException(status_code=409, detail="Sells always execute and cannot be approved or rejected: they remove risk.")
    approvals.record_decision(MARKET, order_id, status, note="dashboard")
    repository.log_event("INFO", "approvals", f"APPROVAL DECISION: {status} {order_id}", {"order_id": order_id, "status": status})
    return _approvals_payload()


@router.post("/api/approvals/{order_id}/approve")
def approve(order_id: str, request: Request) -> Dict[str, Any]:
    return _decide(order_id, approvals.APPROVED, request)


@router.post("/api/approvals/{order_id}/reject")
def reject(order_id: str, request: Request) -> Dict[str, Any]:
    return _decide(order_id, approvals.REJECTED, request)


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=200)


def _kill_payload() -> Dict[str, Any]:
    state = ops_status.kill_switch_status()
    env_on = bool(settings.kill_switch_enabled)
    return {
        **state,
        "env_override": env_on,  # KILL_SWITCH_ENABLED=true in .env cannot be switched off here
        "effective": bool(state.get("enabled")) or env_on,
        "warning": "While the kill switch is ON the nightly run does nothing at all: no buys, no sells, and stop-losses are NOT checked.",
    }


@router.get("/api/kill-switch")
def get_kill_switch() -> Dict[str, Any]:
    return _kill_payload()


@router.post("/api/kill-switch")
def set_kill_switch(body: KillSwitchRequest, request: Request) -> Dict[str, Any]:
    require_local_ui(request)
    reason = " ".join(body.reason.split())  # one tidy line; the state is stored as "enabled|reason"
    if body.enabled and not reason:
        raise HTTPException(status_code=422, detail="Say why you are turning it on, so the log explains the halt later.")
    repository.save_kill_switch_state(body.enabled, reason.replace("|", "/"))
    repository.log_event("WARNING" if body.enabled else "INFO", "approvals",
                         f"KILL SWITCH {'ON' if body.enabled else 'OFF'} set from the dashboard. Reason: {reason or '-'}",
                         {"enabled": body.enabled})
    try:
        from src.alerts.telegram_alerts import notify

        notify(f"{'🛑 KILL SWITCH ON' if body.enabled else '✅ Kill switch off'}\n{reason or 'No reason given.'}")
    except Exception as exc:  # noqa: BLE001 - the switch itself already took effect
        logger.warning("Kill switch alert not sent: %s", exc)
    return _kill_payload()
