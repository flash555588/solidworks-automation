"""LLM integration for cad_ai.

This subpackage is intentionally network-capable.  The rest of cad_ai
stays network-free; the orchestrator (the human or the agent loop)
chooses whether to import from this subpackage.

Public entry point: `cad_ai.llm.text_to_ir(text, **opts)`.  Returns
a validated CAD-IR dict, or raises `cad_ai.llm.errors.LLMError`.

Provider is selected by environment variables:

- `CADPY_AI_LLM_BASE_URL` -- OpenAI-compatible base URL (default
  `http://localhost:11434/v1`, which works with ollama).
- `CADPY_AI_LLM_MODEL` -- model name (default `qwen2.5-coder:7b`).
- `CADPY_AI_LLM_API_KEY` -- API key (default `ollama`, accepted by
from .errors import (
    LLMError,
    LLMHTTPError,
    LLMJSONError,
    LLMValidationError,
    LLMAuthError,
)

# Note: we deliberately do NOT re-export `text_to_ir` as a function
# at the package level.  Doing so would shadow the `text_to_ir`
# submodule and break `import cad_ai.llm.text_to_ir as mod`.  Callers
# that want the function should do:
#
#     from cad_ai.llm.text_to_ir import text_to_ir

__all__ = [
    "LLMError",
    "LLMHTTPError",
    "LLMJSONError",
    "LLMValidationError",
    "LLMAuthError",
]
`build123d`.
"""
__all__ = [
    "LLMError",
    "LLMHTTPError",
    "LLMJSONError",
    "LLMValidationError",
    "LLMAuthError",
]