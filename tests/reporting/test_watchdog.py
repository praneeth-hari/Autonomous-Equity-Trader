"""Watchdog alerts: right alert for the right outcome, once per day, and never a secret."""

from __future__ import annotations

import pytest

from src.alerts import watchdog as wd


class Sent:
    """Stands in for telegram notify(): records messages and honours the dedup key like the real one."""

    def __init__(self):
        self.messages, self.keys = [], set()

    def __call__(self, message, alert_key=None):
        if alert_key in self.keys:
            return False
        self.keys.add(alert_key)
        self.messages.append(message)
        return True


@pytest.mark.parametrize("code", [0, 2])
def test_success_and_degraded_runs_do_not_alert(code):
    sent = Sent()
    assert wd.alert_run_outcome(code, notify_fn=sent) is False and sent.messages == []


def test_crash_alerts_with_the_consequence_and_log_tail(tmp_path):
    log = tmp_path / "daily_run_2026-11-25.log"
    log.write_text("start\nModuleNotFoundError: No module named 'pytz'\nPIPELINE FAILED\n", encoding="utf-8")
    sent = Sent()
    assert wd.alert_run_outcome(1, str(log), "2026-11-25", sent) is True
    msg = sent.messages[0]
    assert "NIGHTLY RUN FAILED" in msg and "No module named 'pytz'" in msg and "stop-losses were NOT checked" in msg


def test_halt_has_its_own_wording():
    sent = Sent()
    wd.alert_run_outcome(3, run_date="2026-11-25", notify_fn=sent)
    assert "HALTED" in sent.messages[0] and "kill switch" in sent.messages[0]


def test_same_failure_alerts_once_per_day_but_a_new_day_alerts_again():
    sent = Sent()
    assert wd.alert_run_outcome(1, run_date="2026-11-25", notify_fn=sent) is True
    assert wd.alert_run_outcome(1, run_date="2026-11-25", notify_fn=sent) is False
    assert wd.alert_run_outcome(1, run_date="2026-11-26", notify_fn=sent) is True


def test_secrets_are_removed_from_alert_text(tmp_path):
    token = "bot8123456789:AAFakeTokenValueForTestingOnly_abcdefghij"  # secret-scan: allow
    log = tmp_path / "run.log"
    log.write_text(f'POST https://api.telegram.org/{token}/sendMessage\napi_key=sk-live-abc123\n'
                   "postgresql://user:hunter2@db.example.com:5432/x\nPIPELINE FAILED\n", encoding="utf-8")
    sent = Sent()
    wd.alert_run_outcome(1, str(log), "2026-11-25", sent)
    text = sent.messages[0]
    for secret in ("AAFakeToken", "sk-live-abc123", "hunter2"):
        assert secret not in text


def test_missed_run_and_environment_alerts():
    sent = Sent()
    assert wd.alert_missed_run("2026-11-24", "2026-11-20", sent) and "MISSED NIGHTLY RUN" in sent.messages[0]
    assert wd.alert_environment_problem(["scikit-learn is not installed"], "2026-11-25", sent)
    assert "not started" in sent.messages[1] and "scikit-learn" in sent.messages[1]


@pytest.mark.parametrize("status, alerts, expect", [
    ("HEALTHY", [], False),
    ("WARNING", ["Notice: nothing special"], False),
    ("WARNING", ["Last pipeline run was 2026-11-20, but expected 2026-11-24."], True),
    ("CRITICAL", ["Latest run failed"], True),
])
def test_health_alert_only_for_critical_or_missed(status, alerts, expect):
    assert wd.alert_health(status, alerts, "2026-11-25", Sent()) is expect


def test_sending_problem_never_raises_and_flags_the_cli(monkeypatch, capsys):
    def boom(*a, **k):
        raise ImportError("No module named 'telegram'")

    assert wd.alert_run_outcome(1, run_date="2026-11-25", notify_fn=boom) is False
    assert wd._STATE["error"]
    monkeypatch.setattr(wd, "alert_run_outcome", lambda *a, **k: wd._send("x", "k", boom))
    assert wd._main(["run", "--exit-code", "1"]) == 1  # non-zero so the batch file retries with system Python
    assert "COULD NOT BE SENT" in capsys.readouterr().out


def test_cli_reports_when_nothing_needed_sending(capsys):
    assert wd._main(["run", "--exit-code", "0"]) == 0
    assert "no alert sent" in capsys.readouterr().out


# ── Wiring: the health check and the batch file really call the watchdog ──────

def test_health_check_pushes_a_critical_result(monkeypatch, tmp_path):
    import health_check

    monkeypatch.setattr(health_check, "LOGS_DIR", tmp_path)
    (tmp_path / "daily_run_2026-11-25.log").write_text("PIPELINE FAILED\n", encoding="utf-8")
    monkeypatch.setattr(health_check, "get_db_health", lambda: {
        "db_connected": True, "total_equity": 1.0, "cash": 1.0, "latest_snapshot_date": "x", "critical_events": [], "total_slippage_cost": 0})
    calls = []
    monkeypatch.setattr(wd, "alert_health", lambda status, alerts, day=None, notify_fn=None: calls.append((status, alerts)) or True)
    assert health_check.run_health_check() == 1
    assert calls and calls[0][0] == "CRITICAL"


def test_health_check_still_returns_its_exit_code_when_sending_fails(monkeypatch, tmp_path):
    import health_check

    monkeypatch.setattr(health_check, "LOGS_DIR", tmp_path)
    (tmp_path / "daily_run_2026-11-25.log").write_text("PIPELINE FAILED\n", encoding="utf-8")
    monkeypatch.setattr(health_check, "get_db_health", lambda: {
        "db_connected": True, "total_equity": 1.0, "cash": 1.0, "latest_snapshot_date": "x", "critical_events": [], "total_slippage_cost": 0})

    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(wd, "alert_health", boom)
    assert health_check.run_health_check() == 1


def test_nightly_batch_file_alerts_on_crash_with_a_system_python_fallback():
    from pathlib import Path

    bat = (Path(__file__).resolve().parents[2] / "run_trader.bat").read_text(encoding="utf-8")
    assert "if %PIPELINE_EXIT% neq 0 if %PIPELINE_EXIT% neq 2 call :ALERT_RUN" in bat
    assert "src.alerts.watchdog run --exit-code" in bat
    assert "py -3 -m src.alerts.watchdog" in bat  # the retry that a broken .venv cannot silence


def test_backup_alert_and_batch_wiring():
    from pathlib import Path

    sent = Sent()
    assert wd.alert_backup_problem("Integrity check failed", "2026-11-25", sent)
    assert "BACKUP FAILED" in sent.messages[0] and "no fresh restore point" in sent.messages[0]
    bat = (Path(__file__).resolve().parents[2] / "run_trader.bat").read_text(encoding="utf-8")
    assert bat.index("%PYTHON_CMD% -m src.ops.backup create") < bat.index("%PYTHON_CMD% -m src.pipeline.scheduler --force >>")  # backup comes first
    assert "if errorlevel 1 call :ALERT_BACKUP" in bat


def test_environment_alert_names_the_failures_from_the_run_log(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("[ OK ] Python 3.11.9\n[FAIL] scikit-learn is not installed (need >=1.5.0).\n"
                   "[FAIL] The model gives different predictions in this environment.\nENVIRONMENT CHECK FAILED\n", encoding="utf-8")
    problems = wd.failures_from_log(str(log))
    assert problems == ["scikit-learn is not installed (need >=1.5.0).", "The model gives different predictions in this environment."]
    sent = Sent()
    wd.alert_environment_problem(problems, "2026-11-25", sent)
    assert "different predictions" in sent.messages[0]


def test_preflight_runs_first_and_stops_the_run_on_failure():
    from pathlib import Path

    bat = (Path(__file__).resolve().parents[2] / "run_trader.bat").read_text(encoding="utf-8")
    pre, backup, run = (bat.index("%PYTHON_CMD% -m src.ops.envcheck"), bat.index("%PYTHON_CMD% -m src.ops.backup create"),
                        bat.index("%PYTHON_CMD% -m src.pipeline.scheduler --force >>"))
    assert pre < backup < run
    block = bat[pre: backup]
    assert "call :ALERT_ENV" in block and "exit /b 1" in block
