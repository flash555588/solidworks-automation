"""Reference implementation of a SOLIDWORKS instruction stream executor.

This is a MOCK: it does not call any COM API.  It re-runs the IR
through `ir_compile.compile_ir` to produce a build123d source, then
evaluates it to get the geometry, and finally writes a STEP file
directly via OCP (OpenCascade).  The cadpy metadata header that
the `scripts/step` CLI adds is intentionally NOT replicated here;
this mock is meant for hosts without SOLIDWORKS, and a real
SOLIDWORKS backend will produce a `.SLDPRT` whose STEP export
includes its own provenance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

from . import ir_compile, ir_validate


def run_mock_sw_with_ir(ir_doc):
    """Run the mock executor on a CAD-IR dict and return a Solid."""
    v = ir_validate.validate_ir(ir_doc)
    if not v["ok"]:
        raise ValueError(f"IR validation failed: {v['errors']}")
    source = ir_compile.compile_ir(ir_doc)
    namespace = {}
    exec(compile(source, "<cad_ai-mock_sw>", "exec"), namespace)
    return namespace["gen_step"]()


def export_step_from_ir(ir_doc, out_path):
    """Run the mock and export the result to STEP via OCP."""
    solid = run_mock_sw_with_ir(ir_doc)
    writer = STEPControl_Writer()
    writer.Transfer(solid.wrapped, STEPControl_AsIs)
    status = writer.Write(str(out_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"OCP STEP write failed with status {status}")
    return solid


def main(argv):
    if len(argv) < 2:
        print("Usage: mock_sw.py <cad-ir.json> [-o <output.step>]", file=sys.stderr)
        return 2
    src = Path(argv[1])
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 >= len(argv):
            print("mock_sw.py: -o requires a path", file=sys.stderr)
            return 2
        out = Path(argv[i + 1])
    try:
        ir_doc = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"mock_sw.py: failed to read {src}: {exc}", file=sys.stderr)
        return 2
    try:
        solid = run_mock_sw_with_ir(ir_doc)
    except ValueError as exc:
        print(f"mock_sw.py: {exc}", file=sys.stderr)
        return 1
    if out is None:
        print(f"ok: {solid.bounding_box()}", file=sys.stderr)
        return 0
    try:
        writer = STEPControl_Writer()
        writer.Transfer(solid.wrapped, STEPControl_AsIs)
        status = writer.Write(str(out))
        if status != IFSelect_RetDone:
            print(f"mock_sw.py: OCP STEP write failed with status {status}",
                  file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"mock_sw.py: STEP write failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
