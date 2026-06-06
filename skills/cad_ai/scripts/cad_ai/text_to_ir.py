"""Stub for text -> CAD-IR.

This skill stays network-free.  A real LLM call lives in the
orchestrator that drives cad_ai; the prompt template to use is
`skills/cad_ai/references/text_to_ir_prompt.md`.

The stub returns None and writes a short explanation.  It exists so
that `from cad_ai.text_to_ir import text_to_ir` is a stable import
that the orchestrator can call (or monkey-patch).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[2] / "references" / "text_to_ir_prompt.md"


def text_to_ir(prompt: str) -> "dict | None":
    """Stub: would call an LLM with the prompt template; returns None.

    A real implementation would:
    1. Read `PROMPT_PATH` for the template.
    2. Substitute `{prompt}` with the user's request.
    3. POST to the configured LLM endpoint (configurable by env vars).
    4. JSON-decode the response.
    5. Run `validate_ir(ir)`; on failure, retry with the error list.
    6. Return the validated dict.
    """
    sys.stderr.write(
        "cad_ai.text_to_ir.text_to_ir is a stub. "
        f"See {PROMPT_PATH} for the prompt template.\n"
    )
    return None


if __name__ == "__main__":
    sys.stderr.write(
        "text_to_ir is a stub; no input is processed. "
        f"Read {PROMPT_PATH} for the prompt template.\n"
    )
    sys.exit(0)
