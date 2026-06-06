"""CLI entry: read 3 DXF views and emit a CAD-IR JSON on stdout."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cad_ai.dxf_to_ir import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
