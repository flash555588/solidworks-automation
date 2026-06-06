"""CLI entry: validate a CAD-IR JSON file."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the local cad_ai package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cad_ai.ir_validate import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
