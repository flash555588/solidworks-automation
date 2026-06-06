"""CLI entry: convert a text prompt to a CAD-IR JSON file via an LLM.

This is the network-capable CLI.  It uses `cad_ai.llm.text_to_ir`
under the hood, which is independent of the network-free stub at
`cad_ai.text_to_ir.text_to_ir`.  The two share the public function
name so that orchestrators can swap the implementation by changing
one import.

Required env vars:
  CADPY_AI_LLM_BASE_URL  OpenAI-compatible base URL (default
                         http://localhost:11434/v1, ollama)
  CADPY_AI_LLM_MODEL     model name (default qwen2.5-coder:7b)
  CADPY_AI_LLM_API_KEY   API key (default "ollama", accepted by
                         ollama without real auth)

Usage:
  python scripts/text_to_ir.py "Mounting plate 100x60x10 with 4x6 holes" \\
      -o /tmp/ir.json
  python scripts/text_to_ir.py --prompt-file prompt.txt -o /tmp/ir.json

Exit code is non-zero on any unrecoverable error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the local cad_ai package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cad_ai.llm import text_to_ir  # noqa: E402


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("prompt", nargs="?", help="inline prompt string")
    src.add_argument("--prompt-file", help="path to a text file containing the prompt")
    p.add_argument("-o", "--output", help="write the IR JSON here (default: stdout)")
    p.add_argument("--max-retries", type=int, default=2,
                    help="number of validation retries (default 2)")
    args = p.parse_args(argv[1:])

    if args.prompt is not None:
        prompt_text = args.prompt
    else:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    try:
        ir = text_to_ir(prompt_text, max_retries=args.max_retries)
    except Exception as exc:
        print(f"text_to_ir: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(ir, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
