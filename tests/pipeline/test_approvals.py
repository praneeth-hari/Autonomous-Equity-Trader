"""Optional human approval (off by default) and the kill switch, proven on real pipeline runs.

The rules under test:
  * Approval OFF (the default): behaviour is exactly the frozen V1 behaviour.
  * Approval ON: a BUY fills only if approved; no decision means no buy; SELLs always fill.
  * Kill switch ON halts the whole run (no fills, nothing written); switching it OFF resumes.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from config.settings import settings
from src.db import repository
from src.pipeline import approvals
from src.portfolio.portfolio import OrderSpec
from src.trading.paper_broker import PaperBroker
from tests.pipeline.test_v1_operational_safety import (  # noqa: F401 - fixtures and helpers reused on purpose
    D, DAYS, PREV, _buy, _commit_day0, _run, _us_trades, fresh_db, quiet,
)


def _sell(ticker, on, shares=10.0, price=100.0, reason="STOP_LOSS"):
    gross = shares * price
    return OrderSpec(date=on, ticker=ticker, action="SELL", order_type="MARKET", shares=shares, reference_price=price,
                     gross_value=gross, estimated_fee=gross * 0.002, net_amount=gross * 0.998, reason=reason)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "human_approval_required", False)
    monkeypatch.setattr(settings, "kill_switch_enabled", False)
    yield
    repository.save_kill_switch_state(False, "")


def _approval_on(monkeypatch):
    monkeypatch.setattr(settings, "human_approval_required", True)


# ── Approval mode ─────────────────────────────────────────────────────────────

def test_off_by_default_so_the_frozen_behaviour_is_unchanged():
    from config.settings import Settings

    assert Settings.model_fields["human_approval_required"].default is False


def test_off_an_unapproved_buy_fills_exactly_as_before(fresh_db, quiet):
    _commit_day0([_buy("AAPL", PREV)])
    _run(D)
    assert [t["ticker"] for t in _us_trades()] == ["AAPL"]


def test_on_a_buy_with_no_decision_is_not_filled_and_the_reason_is_logged(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    _commit_day0([_buy("AAPL", PREV)])
    res = _run(D)
    assert _us_trades() == [] and res.fills == []
    msgs = [e["message"] for e in repository.get_events(limit=50)]
    assert any(m.startswith("APPROVAL: BUY AAPL was not filled") and "no approval was given" in m for m in msgs)
    assert repository.get_latest_portfolio_snapshot("US")["pending_orders"] == []  # not carried over: it must be re-proposed


def test_on_an_approved_buy_fills(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    _commit_day0([_buy("AAPL", PREV)])
    approvals.record_decision("US", approvals.order_id(_buy("AAPL", PREV)), approvals.APPROVED)
    _run(D)
    assert [t["ticker"] for t in _us_trades()] == ["AAPL"]


def test_on_a_rejected_buy_is_not_filled(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    _commit_day0([_buy("AAPL", PREV)])
    approvals.record_decision("US", approvals.order_id(_buy("AAPL", PREV)), approvals.REJECTED)
    _run(D)
    assert _us_trades() == []
    assert any("you rejected it" in e["message"] for e in repository.get_events(limit=50))


def test_on_only_the_approved_buy_of_two_fills(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    _commit_day0([_buy("AAPL", PREV), _buy("MSFT", PREV)])
    approvals.record_decision("US", approvals.order_id(_buy("MSFT", PREV)), approvals.APPROVED)
    _run(D, tickers=("AAPL", "MSFT"))
    assert [t["ticker"] for t in _us_trades()] == ["MSFT"]


def test_on_a_stop_loss_sell_always_fills_without_any_approval(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    held = PaperBroker(market="US")
    held.load_state()
    held.execute_order(order=_buy("AAPL", DAYS[-5]), fill_price=100.0, run_date=DAYS[-4])
    held.sync_pending_orders([_sell("AAPL", PREV)])
    held.record_snapshot(run_date=PREV, current_prices={"AAPL": 100.0})
    _run(D)
    sells = [t for t in _us_trades() if t["action"] == "SELL"]
    assert [t["ticker"] for t in sells] == ["AAPL"]
    assert "AAPL" not in repository.get_latest_portfolio_snapshot("US")["positions"]  # the position is gone


def test_an_approval_for_another_day_or_ticker_does_not_carry_over(fresh_db, quiet, monkeypatch):
    _approval_on(monkeypatch)
    _commit_day0([_buy("AAPL", PREV)])
    approvals.record_decision("US", approvals.order_id(_buy("AAPL", DAYS[-10])), approvals.APPROVED)  # an older proposal
    approvals.record_decision("US", approvals.order_id(_buy("MSFT", PREV)), approvals.APPROVED)       # another stock
    _run(D)
    assert _us_trades() == []


# ── approvals module on its own ───────────────────────────────────────────────

def test_order_id_is_stable_for_objects_and_dicts():
    o = _buy("aapl", "2026-11-25")
    assert approvals.order_id(o) == "2026-11-25:BUY:AAPL" == approvals.order_id(o.to_dict())


def test_a_damaged_decisions_file_approves_nothing(fresh_db, monkeypatch):
    _approval_on(monkeypatch)
    approvals.record_decision("US", "x:BUY:AAPL", approvals.APPROVED)
    approvals._path("US").write_text("{ this is not json", encoding="utf-8")
    assert approvals.load_decisions("US") == {}
    keep, dropped = approvals.filter_for_fill([_buy("AAPL", "x")], "US")
    assert keep == [] and len(dropped) == 1


def test_decisions_are_written_atomically_and_validated(fresh_db):
    with pytest.raises(ValueError):
        approvals.record_decision("US", "a:BUY:B", "MAYBE")
    approvals.record_decision("US", "a:BUY:B", approvals.APPROVED, note="x" * 500)
    data = json.loads(approvals._path("US").read_text(encoding="utf-8"))
    assert len(data["decisions"]["a:BUY:B"]["note"]) == 200
    assert not approvals._path("US").with_suffix(".tmp").exists()


def test_old_decisions_are_pruned(fresh_db):
    from datetime import datetime, timedelta, timezone

    approvals.record_decision("US", "old:BUY:A", approvals.APPROVED)
    approvals.record_decision("US", "new:BUY:B", approvals.APPROVED)
    data = json.loads(approvals._path("US").read_text(encoding="utf-8"))
    data["decisions"]["old:BUY:A"]["decided_at"] = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    approvals._path("US").write_text(json.dumps(data), encoding="utf-8")
    assert approvals.prune("US") == 1 and list(approvals.load_decisions("US")) == ["new:BUY:B"]


def test_announcement_only_when_on_and_there_are_buys(monkeypatch):
    sent = []
    import src.alerts.telegram_alerts as ta

    monkeypatch.setattr(ta, "notify", lambda msg, alert_key=None: sent.append(msg) or True)
    assert approvals.announce_pending([_buy("AAPL", "d")], "d") is False  # mode off
    _approval_on(monkeypatch)
    assert approvals.announce_pending([_sell("AAPL", "d")], "d") is False  # only sells
    assert approvals.announce_pending([_buy("AAPL", "d")], "d") is True
    assert "AAPL" in sent[0] and "No approval means no buy" in sent[0]


# ── Kill switch ───────────────────────────────────────────────────────────────

def test_kill_switch_halts_the_run_and_switching_it_off_resumes(fresh_db, quiet):
    _commit_day0([_buy("AAPL", PREV)])
    repository.save_kill_switch_state(True, "testing the halt")

    halted = _run(D)
    assert halted.regime == "KILL_SWITCH_ACTIVE" and halted.status == "HALTED"
    assert halted.fills == [] and halted.orders_generated == 0
    assert "testing the halt" in halted.errors[0]
    assert _us_trades() == []
    assert repository.get_portfolio_snapshot(D, "US") is None, "a halted run writes nothing"
    assert [o["ticker"] for o in repository.get_latest_portfolio_snapshot("US")["pending_orders"]] == ["AAPL"], "the queued order waits"
    assert settings.kill_switch_enabled is False, "the persisted switch must not be copied into settings"

    repository.save_kill_switch_state(False, "")
    resumed = _run(D)
    assert resumed.regime != "KILL_SWITCH_ACTIVE" and [t["ticker"] for t in _us_trades()] == ["AAPL"]


def test_environment_override_halts_even_when_the_persisted_switch_is_off(fresh_db, quiet, monkeypatch):
    _commit_day0([_buy("AAPL", PREV)])
    monkeypatch.setattr(settings, "kill_switch_enabled", True)
    monkeypatch.setattr(settings, "kill_switch_reason", "set in .env")
    repository.save_kill_switch_state(False, "")
    res = _run(D)
    assert res.status == "HALTED" and "set in .env" in res.errors[0] and _us_trades() == []


def test_a_kill_switch_halt_is_logged_for_the_record(fresh_db, quiet):
    repository.save_kill_switch_state(True, "audit trail")
    _run(D)
    assert any("EMERGENCY KILL SWITCH ACTIVE" in e["message"] and "audit trail" in e["message"] for e in repository.get_events(limit=50))


def test_the_nightly_exit_code_for_a_halt_alerts_you():
    """Exit code 3 (halted) reaches the watchdog, so you hear about it if the switch was left on."""
    from src.alerts import watchdog as wd

    sent = []
    assert wd.alert_run_outcome(3, run_date="2026-11-25", notify_fn=lambda m, alert_key=None: sent.append(m) or True)
    assert "HALTED" in sent[0]
