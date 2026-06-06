"""CLI entry: compile a CAD-IR JSON file to a SW instruction stream."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cad_ai.sw_compile import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
