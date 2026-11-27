"""Approvals and kill-switch routes: what they allow, and the guards that keep other sites out."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from src.api import ops_routes
from src.api.app import app
from src.db import repository
from src.pipeline import approvals

client = TestClient(app)
UI = {"X-Requested-With": "paper-trader", "Origin": "http://127.0.0.1:5173"}

BUY = {"date": "2026-11-25", "ticker": "AAPL", "action": "BUY", "shares": 4.0, "reference_price": 200.0, "gross_value": 800.0, "reason": "QUALIFIED_CONVICTION_BUY"}
SELL = {"date": "2026-11-25", "ticker": "META", "action": "SELL", "shares": 1.5, "reference_price": 590.0, "gross_value": 885.0, "reason": "STOP_LOSS"}
BUY_ID, SELL_ID = "2026-11-25:BUY:AAPL", "2026-11-25:SELL:META"


@pytest.fixture(autouse=True)
def world(monkeypatch):
    monkeypatch.setattr(settings, "human_approval_required", True)
    monkeypatch.setattr(settings, "kill_switch_enabled", False)
    monkeypatch.setattr(ops_routes.repository, "get_latest_portfolio_snapshot", lambda market="US": {"run_date": "2026-11-25", "pending_orders": [BUY, SELL]})
    p = approvals._path("US")
    if p.exists():
        p.unlink()
    yield
    repository.save_kill_switch_state(False, "")


def test_list_shows_buys_awaiting_a_decision_and_sells_as_automatic():
    body = client.get("/api/approvals").json()
    by = {o["id"]: o for o in body["orders"]}
    assert body["approval_required"] is True and body["run_date"] == "2026-11-25"
    assert by[BUY_ID]["status"] == "PENDING" and by[BUY_ID]["requires_approval"] is True
    assert by[SELL_ID]["status"] == "AUTO" and by[SELL_ID]["requires_approval"] is False
    assert any("No decision means no buy" in line for line in body["how_it_works"])


def test_approve_then_reject_the_latest_decision_wins():
    r = client.post(f"/api/approvals/{BUY_ID}/approve", headers=UI)
    assert r.status_code == 200 and {o["id"]: o for o in r.json()["orders"]}[BUY_ID]["status"] == "APPROVED"
    assert approvals.load_decisions("US")[BUY_ID]["status"] == "APPROVED"
    r = client.post(f"/api/approvals/{BUY_ID}/reject", headers=UI)
    assert {o["id"]: o for o in r.json()["orders"]}[BUY_ID]["status"] == "REJECTED"


def test_a_decision_is_written_to_the_event_log():
    client.post(f"/api/approvals/{BUY_ID}/approve", headers=UI)
    assert any(f"APPROVAL DECISION: APPROVED {BUY_ID}" in e["message"] for e in repository.get_events(limit=20))


def test_sells_cannot_be_approved_or_rejected():
    for action in ("approve", "reject"):
        r = client.post(f"/api/approvals/{SELL_ID}/{action}", headers=UI)
        assert r.status_code == 409 and "remove risk" in r.json()["detail"]
    assert approvals.load_decisions("US") == {}


def test_unknown_order_is_404_and_leaves_no_trace():
    r = client.post("/api/approvals/2026-11-25:BUY:ZZZZ/approve", headers=UI)
    assert r.status_code == 404 and approvals.load_decisions("US") == {}


def test_when_approval_mode_is_off_a_decision_is_refused_not_silently_ignored(monkeypatch):
    monkeypatch.setattr(settings, "human_approval_required", False)
    r = client.post(f"/api/approvals/{BUY_ID}/approve", headers=UI)
    assert r.status_code == 409 and "Approval mode is off" in r.json()["detail"]
    assert "HUMAN_APPROVAL_REQUIRED" in client.get("/api/approvals").json()["enable_hint"]


@pytest.mark.parametrize("headers", [
    {},                                                                   # no marker header
    {"X-Requested-With": "paper-trader", "Origin": "http://evil.example"},  # right header, wrong site
    {"X-Requested-With": "XMLHttpRequest", "Origin": "http://127.0.0.1:5173"},
])
def test_state_changing_routes_refuse_requests_that_do_not_come_from_the_web_app(headers):
    # Each check reports what actually came back: this test failed once (2026-11-26, PC very short of memory)
    # and the cause could not be reproduced, so a repeat must explain itself.
    r = client.post(f"/api/approvals/{BUY_ID}/approve", headers=headers)
    assert r.status_code == 403, f"approve with {headers}: {r.status_code} {r.text[:300]}"
    r = client.post("/api/kill-switch", json={"enabled": True, "reason": "x"}, headers=headers)
    assert r.status_code == 403, f"kill switch with {headers}: {r.status_code} {r.text[:300]}"
    decisions = approvals.load_decisions("US")
    assert decisions == {}, f"decisions written despite the refusal: {decisions} (file {approvals._path('US')})"
    assert repository.load_kill_switch_state()[0] is False, "kill switch was switched on despite the refusal"
    assert client.get("/api/kill-switch").json()["enabled"] is False


def test_browsers_from_other_origins_get_no_cors_permission():
    r = client.options("/api/kill-switch", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_kill_switch_needs_a_reason_to_turn_on():
    r = client.post("/api/kill-switch", json={"enabled": True, "reason": "   "}, headers=UI)
    assert r.status_code == 422 and repository.load_kill_switch_state()[0] is False


def test_kill_switch_on_then_off_is_reflected_and_clearly_warned():
    with patch("src.alerts.telegram_alerts.notify", return_value=True) as notify:
        on = client.post("/api/kill-switch", json={"enabled": True, "reason": "market looks wrong | check\nlater"}, headers=UI).json()
        assert on["enabled"] is True and on["effective"] is True and "stop-losses are NOT checked" in on["warning"]
        assert "|" not in on["reason"] and "\n" not in on["reason"]  # stored as a single tidy line
        assert repository.load_kill_switch_state()[0] is True
        off = client.post("/api/kill-switch", json={"enabled": False}, headers=UI).json()
        assert off["enabled"] is False and off["effective"] is False
    assert notify.call_count == 2
    assert any("KILL SWITCH ON set from the dashboard" in e["message"] for e in repository.get_events(limit=20))


def test_an_environment_override_cannot_be_switched_off_from_the_dashboard(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", True)
    body = client.post("/api/kill-switch", json={"enabled": False}, headers=UI).json()
    assert body["enabled"] is False and body["env_override"] is True and body["effective"] is True


def test_the_switch_works_even_if_the_alert_cannot_be_sent():
    with patch("src.alerts.telegram_alerts.notify", side_effect=RuntimeError("telegram down")):
        r = client.post("/api/kill-switch", json={"enabled": True, "reason": "x"}, headers=UI)
    assert r.status_code == 200 and repository.load_kill_switch_state()[0] is True


def test_reading_state_needs_no_header():
    assert client.get("/api/approvals").status_code == 200 and client.get("/api/kill-switch").status_code == 200


def test_the_complete_list_of_routes_that_change_anything_is_fixed():
    """Any new write route must be added here on purpose. None of them can place, size or price a trade."""
    paths = app.openapi()["paths"]
    writers = {p for p, ops in paths.items() if any(m in ops for m in ("post", "put", "patch", "delete"))}
    assert writers == {"/api/chat", "/api/approvals/{order_id}/approve", "/api/approvals/{order_id}/reject", "/api/kill-switch"}
    assert not any("order" in p.replace("{order_id}", "") or "trade" in p for p in writers)
