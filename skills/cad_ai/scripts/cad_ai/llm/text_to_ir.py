"""text -> CAD-IR via an OpenAI-compatible LLM endpoint.

This is the real implementation of `text_to_ir`.  The stand-alone
stub lives at `cad_ai.text_to_ir.text_to_ir` and is the one that
runs by default.  The orchestrator can opt into the network-capable
variant by importing from this subpackage:

    from cad_ai.llm import text_to_ir

Configuration is via environment variables (see `client.py`).

The retry loop is bounded: up to `max_retries` (default 2) attempts
to recover from validation failures by re-prompting the model with
the validator's error list appended.  HTTP / JSON errors do not
trigger retries; they bubble up to the caller.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .client import chat
from .errors import LLMJSONError, LLMValidationError
from ..ir_validate import validate_ir


# Location of the prompt template, relative to the skill root.
PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "references" / "text_to_ir_prompt.md"
)


def _load_prompt_template() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Strip the leading "## Stubs (no LLM...)" section so the
    # production prompt reads cleanly when sent to the model.
    if "## Stubs" in text:
        text = text.split("## Stubs", 1)[0]
    return text


def _extract_json(text):
    """Extract the first JSON object from the LLM response.

    Tolerant of common shapes: a raw object, a code-fenced block,
    or text that surrounds a JSON object.
    """
    text = text.strip()
    # Code fence
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    # First balanced object
    start = text.find("{")
    if start < 0:
        raise LLMJSONError(f"LLM response has no JSON object: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise LLMJSONError(f"LLM response JSON never closed: {text[:200]!r}")


def _build_messages(prompt, errors=None):
    template = _load_prompt_template()
    user_text = template.replace("<<<\n{prompt}\n>>>", prompt)
    if errors:
        bullet = "\n".join(f"- {e['path']}: {e['message']}" for e in errors)
        user_text += (
            "\n\nYour previous attempt failed CAD-IR validation with the "
            "following errors. Fix them and emit a corrected JSON object:\n"
            f"{bullet}\n"
        )
    return [
        {"role": "system", "content": (
            "You are a CAD planning assistant. Emit only a single JSON "
            "object that matches the CAD-IR v0 schema. No commentary."
        )},
        {"role": "user", "content": user_text},
    ]


def text_to_ir(prompt, *, max_retries=2, model=None, base_url=None, api_key=None):
    """Convert a free-form text prompt to a validated CAD-IR dict.

    Returns the validated dict.  Raises LLMError subclasses on
    unrecoverable failures.
    """
    import os
    if model is not None:
        os.environ["CADPY_AI_LLM_MODEL"] = model
    if base_url is not None:
        os.environ["CADPY_AI_LLM_BASE_URL"] = base_url
    if api_key is not None:
        os.environ["CADPY_AI_LLM_API_KEY"] = api_key

    errors = None
    raw = None
    for attempt in range(max_retries + 1):
        messages = _build_messages(prompt, errors=errors)
        text = chat(messages)
        raw = text
        try:
            ir = _extract_json(text)
        except LLMJSONError:
            # Bad JSON is not retriable through the validator loop; the
            # same model will just emit bad JSON again.  We retry once
            # with a stronger instruction.
            if attempt < max_retries:
                errors = None
                continue
            raise
        v = validate_ir(ir)
        if v["ok"]:
            return ir
        errors = v["errors"]
        if attempt == max_retries:
            raise LLMValidationError(errors=errors, raw=raw)
    # Unreachable.
    raise LLMValidationError(errors=errors, raw=raw)
