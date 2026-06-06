"""OpenAI-compatible HTTP client for cad_ai.  No third-party SDK."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from .errors import LLMAuthError, LLMHTTPError, LLMJSONError


DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_API_KEY = "ollama"


def _resolve_config():
    base_url = os.environ.get("CADPY_AI_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("CADPY_AI_LLM_MODEL", DEFAULT_MODEL)
    api_key = os.environ.get("CADPY_AI_LLM_API_KEY", DEFAULT_API_KEY)
    return base_url, model, api_key


def _http_post_json(url, headers, payload, timeout=60):
    """POST a JSON payload and return the parsed JSON response.

    Raises `LLMAuthError` for HTTP 401/403, `LLMHTTPError` for other
    non-2xx, and `LLMJSONError` if the body is not JSON.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise LLMAuthError(f"LLM auth failed: {body_text[:200]!r}") from exc
        raise LLMHTTPError(exc.code, body_text) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMJSONError(
            f"LLM returned non-JSON: {body[:200]!r}"
        ) from exc


def chat(messages, *, temperature=0.2, max_tokens=2048, timeout=60):
    """Send a chat completion request to an OpenAI-compatible endpoint.

    `messages` is a list of dicts with `role` and `content` keys.
    Returns the assistant message content as a string.
    """
    base_url, model, api_key = _resolve_config()
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    response = _http_post_json(url, headers, payload, timeout=timeout)
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMJSONError(
            f"LLM response shape unexpected: {str(response)[:200]!r}"
        ) from exc
