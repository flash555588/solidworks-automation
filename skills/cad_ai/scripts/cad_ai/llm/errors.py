"""Errors raised by the LLM integration."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for LLM integration errors."""


class LLMAuthError(LLMError):
    """The provider rejected our credentials (HTTP 401/403)."""


class LLMHTTPError(LLMError):
    """The provider returned a non-2xx status other than auth."""

    def __init__(self, status, body):
        super().__init__(f"LLM HTTP {status}: {body[:200]!r}")
        self.status = status
        self.body = body


class LLMJSONError(LLMError):
    """The LLM response was not valid JSON or did not contain a dict."""


class LLMValidationError(LLMError):
    """The LLM returned a CAD-IR dict that failed validation.

    The original validation errors are exposed via `.errors`.
    """

    def __init__(self, errors, raw=None):
        super().__init__(
            f"LLM output failed CAD-IR validation: {len(errors)} error(s)"
        )
        self.errors = errors
        self.raw = raw
