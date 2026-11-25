"""Health-page facts: run history, backup age, skipped stocks, kill switch. Fails soft, never leaks secrets."""

from __future__ import annotations

from datetime import date, datetime

from src.services import ops_status as ops


def _log(d, name, text):
    (d / f"daily_run_{name}.log").write_text(text, encoding="utf-8")


def test_run_history_reads_the_last_marker_and_marks_missed_weekdays(tmp_path):
    _log(tmp_path, "2026-11-23", "[ERROR] PIPELINE FAILED with exit code 1\nPIPELINE FAILED: x\n")
    _log(tmp_path, "2026-11-24", "[WARNING] stuff\n[DEGRADED] Pipeline completed\n")
    _log(tmp_path, "2026-11-25", "PIPELINE FAILED: first try\n[SUCCESS] Pipeline execution finished\n")  # re-run fixed it
    hist = ops.run_history(tmp_path, today=date(2026, 11, 26), days=7)  # Thu 20 .. Wed 26? (7 days ending Thu 26)
    by = {h["date"]: h["outcome"] for h in hist}
    assert by["2026-11-23"] == "FAILED" and by["2026-11-24"] == "DEGRADED" and by["2026-11-25"] == "SUCCESS"
    assert by["2026-11-20"] == "MISSED"  # a Friday with no log
    assert "2026-11-21" not in by and "2026-11-22" not in by  # the weekend is not a missed run
    assert "2026-11-26" not in by  # today has simply not run yet


def test_a_log_without_any_marker_is_unknown_not_success(tmp_path):
    _log(tmp_path, "2026-11-25", "started\nnothing conclusive\n")
    assert ops.run_history(tmp_path, today=date(2026, 11, 26), days=2)[-1]["outcome"] == "UNKNOWN"


def test_run_history_survives_a_missing_logs_folder(tmp_path):
    assert all(h["outcome"] == "MISSED" for h in ops.run_history(tmp_path / "nope", today=date(2026, 11, 26), days=3))


def test_backup_status_reports_age_and_staleness(tmp_path):
    from src.ops import backup as bk

    db = tmp_path / "trader.db"
    db.write_bytes(b"x")
    url = f"sqlite:///{db.as_posix()}"
    assert ops.backup_status(url)["count"] == 0
    d = bk.backup_dir(db)
    d.mkdir()
    (d / "trader_20261124_033000.db").write_bytes(b"x" * 1000)
    (d / "trader_pre_backfill_20260926_002425.db").write_bytes(b"mine")  # manual copy is ignored
    st = ops.backup_status(url, now=datetime(2026, 11, 25, 15, 30))
    assert st["count"] == 1 and st["age_hours"] == 36.0 and st["stale"] is False
    assert ops.backup_status(url, now=datetime(2026, 11, 27, 15, 30))["stale"] is True


def test_backup_status_for_a_non_sqlite_database_says_so():
    st = ops.backup_status("postgresql://u:p@h/db")
    assert st["supported"] is False and "SQLite" in st["message"]


def test_skipped_tickers_come_from_the_latest_run_only(monkeypatch):
    events = [
        {"timestamp": "2026-11-25T09:55:00", "message": "SKIP UNH: validation failed — spike on 2025-04-17"},
        {"timestamp": "2026-11-25T09:55:01", "message": "Pipeline complete"},
        {"timestamp": "2026-11-24T09:55:00", "message": "SKIP TSLA: validation failed — old"},
    ]
    import src.db.repository as repo

    monkeypatch.setattr(repo, "get_events", lambda **k: events)
    out = ops.skipped_tickers()
    assert out["date"] == "2026-11-25" and [s["ticker"] for s in out["skipped"]] == ["UNH"]


def test_facts_fail_soft(monkeypatch):
    import src.db.repository as repo

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(repo, "get_events", boom)
    monkeypatch.setattr(repo, "load_kill_switch_state", boom)
    assert "Could not read" in ops.skipped_tickers()["message"]
    assert ops.kill_switch_status()["enabled"] is None


def test_alert_status_never_exposes_the_secrets(monkeypatch):
    monkeypatch.setattr(ops.settings, "telegram_bot_token", "123456:SECRETSECRETSECRETSECRETSECRET")
    monkeypatch.setattr(ops.settings, "telegram_chat_id", "42")
    out = ops.alerts_status()
    assert out == {"telegram_configured": True, "heartbeat_configured": False} and "SECRET" not in str(out)


def test_environment_status_is_cached_and_survives_errors(monkeypatch):
    from src.ops import envcheck

    ops.clear_cache()
    calls = []
    monkeypatch.setattr(envcheck, "run_checks", lambda: calls.append(1) or envcheck.Result(info=["ok"]))
    ops.environment_status()
    ops.environment_status()
    assert len(calls) == 1
    ops.clear_cache()
    monkeypatch.setattr(envcheck, "run_checks", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ops.environment_status()["ok"] is False


def test_data_quality_lists_problem_tickers_and_is_cached(monkeypatch):
    from src.ops import data_audit as da

    ops.clear_cache()
    calls = []
    bad = da.TickerAudit(ticker="AAPL", rows=10, longest_hole=56, hole_range="2024-07-01 to 2024-09-18")
    good = da.TickerAudit(ticker="MSFT", rows=10)
    monkeypatch.setattr(da, "audit", lambda tickers, **k: calls.append(1) or [bad, good])
    out = ops.data_quality()
    ops.data_quality()
    assert out["checked"] == 2 and [p["ticker"] for p in out["problems"]] == ["AAPL"] and "56 consecutive" in out["problems"][0]["issues"][0]
    assert len(calls) == 1
    ops.clear_cache()
    monkeypatch.setattr(da, "audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    assert "could not run" in ops.data_quality()["message"]
