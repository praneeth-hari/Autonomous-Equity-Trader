"""
src/llm/ollama_client.py — One small, local-only client for Ollama's chat API.

Rules:
  * Local only: the server URL must be localhost/127.0.0.1/::1, so portfolio data and
    headlines are never sent to an outside service.
  * Fail loud: any problem raises OllamaError; callers decide how to degrade
    (the chatbot shows a friendly message, the sentiment scorer falls back to VADER).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class OllamaError(RuntimeError):
    """The local model could not be reached or gave no usable answer."""


def is_local_url(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in _LOCAL_HOSTS


def is_available(base_url: Optional[str] = None, timeout: float = 2.0) -> bool:
    """True when the local Ollama server answers. Never raises; never contacts a non-local host."""
    url = str(base_url or settings.ollama_base_url).strip().rstrip("/")
    if not is_local_url(url):
        return False
    try:
        return requests.get(f"{url}/api/tags", timeout=timeout).ok
    except Exception:  # noqa: BLE001 - "not reachable" is the answer
        return False


def chat(
    messages: List[Dict[str, str]],
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    temperature: Optional[float] = None,
) -> str:
    """Send chat messages to the local Ollama server and return the reply text."""
    url = str(base_url or settings.ollama_base_url).strip().rstrip("/")
    model_name = str(model or settings.ollama_model).strip()

    if not is_local_url(url):
        raise OllamaError(f"Refusing to use non-local LLM host: {url}")

    options: Dict[str, object] = {"num_ctx": settings.ollama_num_ctx}
    if temperature is not None:
        options["temperature"] = temperature

    try:
        resp = requests.post(
            f"{url}/api/chat",
            json={"model": model_name, "messages": messages, "stream": False, "options": options},
            timeout=timeout if timeout is not None else settings.ollama_timeout_seconds,
        )
        resp.raise_for_status()
        text = str((resp.json().get("message") or {}).get("content", "")).strip()
    except Exception as exc:  # noqa: BLE001 - re-raised as OllamaError with the cause
        raise OllamaError(f"Ollama call failed ({url}, model={model_name}): {exc}") from exc

    if not text:
        raise OllamaError(f"Ollama returned an empty reply (model={model_name})")
    return text
