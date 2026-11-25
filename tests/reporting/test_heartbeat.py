"""Heartbeat: right URL per state, off by default, never raises, never logs the URL."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.alerts import heartbeat as hb

URL = "https://hc-ping.com/11111111-2222-3333-4444-555555555555"  # secret-scan: allow


@pytest.mark.parametrize("state, suffix", [("start", "/start"), ("ok", ""), ("fail", "/fail")])
def test_each_state_hits_the_right_address(state, suffix):
    with patch("requests.post", return_value=MagicMock(status_code=200)) as post:
        assert hb.ping(state, "exit code 0", url=URL) is True
    assert post.call_args.args[0] == URL + suffix


def test_off_by_default_nothing_is_sent():
    with patch("requests.post") as post:
        assert hb.ping("ok", url="") is False
    post.assert_not_called()
    from config.settings import Settings

    assert Settings.model_fields["healthcheck_ping_url"].default == ""


@pytest.mark.parametrize("bad", ["ftp://example.com/x", "not a url", "https://user:pw@example.com/x", "file:///etc/passwd", "   "])
def test_unsafe_or_malformed_urls_are_refused(bad):
    assert hb.clean_url(bad) is None
    with patch("requests.post") as post:
        assert hb.ping("ok", url=bad) is False
    post.assert_not_called()


def test_a_self_hosted_plain_http_address_is_allowed():
    assert hb.clean_url("http://192.168.1.20:8000/ping/abc/") == "http://192.168.1.20:8000/ping/abc"


def test_the_message_is_short_and_plain_and_carries_no_portfolio_data():
    with patch("requests.post", return_value=MagicMock(status_code=200)) as post:
        hb.ping("fail", "exit code 1 <script>alert(1)</script>" + "x" * 500, url=URL)
    body = post.call_args.kwargs["data"].decode()
    assert len(body) <= 200 and "<" not in body and ">" not in body


def test_network_errors_never_raise_and_the_url_is_never_logged(caplog):
    with patch("requests.post", side_effect=ConnectionError(f"could not reach {URL}")):
        with caplog.at_level("INFO"):
            assert hb.ping("start", url=URL) is False
    assert "11111111" not in caplog.text and "hc-ping.com" not in caplog.text and "HEARTBEAT_FAILED" in caplog.text


def test_a_rejected_ping_is_reported_as_false_without_the_url(caplog):
    with patch("requests.post", return_value=MagicMock(status_code=404)):
        with caplog.at_level("WARNING"):
            assert hb.ping("ok", url=URL) is False
    assert "status=404" in caplog.text and "11111111" not in caplog.text


def test_unknown_state_is_a_programming_error():
    with pytest.raises(ValueError):
        hb.ping("maybe", url=URL)


def test_the_cli_never_fails_the_run_and_says_when_it_is_not_configured(capsys):
    with patch.object(hb.settings, "healthcheck_ping_url", ""):
        assert hb._main(["ok"]) == 0
    assert "not configured" in capsys.readouterr().out
    with patch.object(hb.settings, "healthcheck_ping_url", URL), patch.object(hb, "ping", return_value=False):
        assert hb._main(["fail", "--message", "x"]) == 0  # a failed ping must not change the exit code
    assert "could not be sent" in capsys.readouterr().out


def test_status_shows_only_that_it_is_configured_never_the_address():
    from src.services import ops_status

    with patch.object(hb.settings, "healthcheck_ping_url", URL):
        out = ops_status.alerts_status()
    assert out["heartbeat_configured"] is True and "hc-ping" not in str(out) and "1111" not in str(out)


def test_the_nightly_batch_file_pings_start_end_and_failure_in_order():
    bat = (Path(__file__).resolve().parents[2] / "run_trader.bat").read_text(encoding="utf-8")
    start = bat.index("src.alerts.heartbeat start")
    pre = bat.index("%PYTHON_CMD% -m src.ops.envcheck")
    run = bat.index("%PYTHON_CMD% -m src.pipeline.scheduler --force >>")
    end_ok = bat.index("src.alerts.heartbeat ok")
    assert start < pre < run < end_ok
    assert "src.alerts.heartbeat fail" in bat
