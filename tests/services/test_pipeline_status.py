"""get_last_pipeline_status: a per-ticker data skip must never read as a failed run."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services import data_loader


def _ev(ts: str, component: str, level: str, message: str) -> dict:
    return {"timestamp": ts, "component": component, "level": level, "message": message}


def _status(events: list[dict]) -> dict:
    def fake_get_events(level=None, component=None, limit=100):
        rows = [e for e in events if component is None or e["component"] == component]
        return sorted(rows, key=lambda e: e["timestamp"], reverse=True)[:limit]

    with patch.object(data_loader.repository, "ensure_schema"), \
         patch.object(data_loader.repository, "get_events", side_effect=fake_get_events):
        return data_loader.get_last_pipeline_status()


UNH_SKIP = "SKIP UNH: validation failed — UNH: dynamic price spike(s) beyond 10x avg daily move"


def test_unh_skip_after_a_degraded_run_does_not_show_failed():
    """The reported bug: a newer manual run logged only SKIP lines, and the status turned FAILED."""
    events = [
        _ev("2026-09-28T22:01:33", "scheduler", "WARNING", "Scheduled pipeline run completed for 2026-09-29 (88.1s). Status=DEGRADED — SKIP TSLA"),
        _ev("2026-10-01T05:44:24", "daily_pipeline", "WARNING", UNH_SKIP),
    ]
    assert _status(events)["status"] == "DEGRADED"


def test_only_ticker_skips_means_no_run_outcome_not_failed():
    assert _status([_ev("2026-10-01T05:44:24", "daily_pipeline", "WARNING", UNH_SKIP)])["status"] == "NO_RUNS"


def test_explicit_failed_status_still_reported():
    events = [_ev("2026-10-01T06:00:00", "scheduler", "ERROR", "Scheduled pipeline run completed for 2026-10-01 (3.0s). Status=FAILED — SPY fetch failed")]
    assert _status(events)["status"] == "FAILED"


def test_error_level_event_is_a_real_failure():
    events = [_ev("2026-10-01T06:00:00", "daily_pipeline", "ERROR", "Database write error, run stopped")]
    assert _status(events)["status"] == "FAILED"


def test_warning_that_merely_contains_failed_is_not_a_failure():
    events = [_ev("2026-10-01T06:00:00", "daily_pipeline", "WARNING", "Telegram alert failed to send; continuing")]
    assert _status(events)["status"] == "NO_RUNS"


@pytest.mark.parametrize("word", ["DEGRADED", "HALTED", "SKIPPED"])
def test_other_explicit_statuses_pass_through(word):
    events = [_ev("2026-10-01T06:00:00", "scheduler", "WARNING", f"Scheduled pipeline run completed. Status={word}")]
    assert _status(events)["status"] == word


def test_success_on_clean_run():
    events = [_ev("2026-10-01T06:00:00", "daily_pipeline", "INFO", "Pipeline complete for 2026-10-01")]
    assert _status(events)["status"] == "SUCCESS"


def test_unrelated_event_noise_cannot_hide_the_last_run():
    """market_data chatter is not even requested, so it cannot push a real run out of view."""
    events = [_ev("2026-09-28T22:01:33", "scheduler", "INFO", "Scheduled pipeline run completed. Status=DEGRADED")]
    events += [_ev(f"2026-11-25T05:{i:02d}:00", "market_data", "INFO", "DATA_SOURCE: yfinance (primary)") for i in range(60)]
    assert _status(events)["status"] == "DEGRADED"
