"""
tests/dashboard/test_chatbot.py — Unit tests for OPTION C: local-LLM (Ollama) chatbot.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.data_loader import ask_chatbot_trigger
from src.chatbot.local_chat import (
    FRIENDLY_ERROR_MSG,
    ask_local_chatbot,
    build_live_context_strings,
    generate_system_prompt,
)


def test_build_live_context_strings():
    ctx = build_live_context_strings()
    assert "portfolio_data" in ctx
    assert "recent_trades" in ctx
    assert "active_alerts" in ctx
    assert "model_rankings" in ctx


def test_generate_system_prompt():
    prompt = generate_system_prompt()
    assert "paper stock trading system" in prompt.lower()
    assert "Current Portfolio Data:" in prompt
    assert "Recent Trades:" in prompt
    assert "Active Alerts:" in prompt
    assert "Model Rankings Today:" in prompt


def _ollama_reply(text: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"message": {"role": "assistant", "content": text}}
    return resp


def test_ask_local_chatbot_success_sends_context_and_history():
    with patch("src.llm.ollama_client.requests.post", return_value=_ollama_reply("  Your portfolio is flat.  ")) as post:
        res = ask_local_chatbot(
            "How is my portfolio doing?",
            chat_history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
            model_name="test-model",
        )
    assert res == "Your portfolio is flat."
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]
    assert url.endswith("/api/chat")
    assert body["model"] == "test-model" and body["stream"] is False
    assert body["options"]["num_ctx"] > 0
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert "Current Portfolio Data:" in body["messages"][0]["content"]


def test_ask_local_chatbot_fallback_when_ollama_down():
    with patch("src.llm.ollama_client.requests.post", side_effect=ConnectionError("refused")):
        assert ask_local_chatbot("What is my win rate?") == FRIENDLY_ERROR_MSG


def test_ask_local_chatbot_fallback_on_empty_reply():
    with patch("src.llm.ollama_client.requests.post", return_value=_ollama_reply("")):
        assert ask_local_chatbot("hello") == FRIENDLY_ERROR_MSG


def test_ask_local_chatbot_refuses_non_local_host():
    """Portfolio data must never be sent to an outside server."""
    with patch("src.llm.ollama_client.requests.post") as post:
        res = ask_local_chatbot("hello", base_url="https://api.example.com")
    assert res == FRIENDLY_ERROR_MSG
    post.assert_not_called()


def test_ask_chatbot_trigger_wrapper():
    with patch("src.chatbot.local_chat.ask_local_chatbot", return_value="Your win rate is 62.5%!") as mock_ask:
        reply = ask_chatbot_trigger("What is my win rate?")
        assert reply == "Your win rate is 62.5%!"
        mock_ask.assert_called_once()
