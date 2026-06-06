"""Unit tests for ir_compile.py sweep emission.

These are string-match tests: build123d is not installed on the
host, so we verify the emitted Python source contains the expected
calls rather than executing it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent / "scripts"))

from cad_ai.ir_compile import compile_ir  # type: ignore


class TestIrCompileSweep(unittest.TestCase):
    def _minimal_doc(self, features, params):
        return {
            "schema": "cad_ir.v0",
            "units": "mm",
            "document": {"type": "part", "name": "test"},
            "coordinate_system": {
                "origin": "part_center",
                "up_axis": "Z",
                "front_axis": "Y",
            },
            "parameters": params,
            "features": features,
        }

    def test_imports_contain_line_and_sweep(self):
        doc = self._minimal_doc(
            [
                {"id": "b", "type": "extrude_add",
                 "sketch": {"plane": "XY",
                   "entities": [{"type": "center_rectangle",
                     "center": [0, 0], "size": [10, 10]}]},
                 "depth": "base_depth", "direction": "+Z"},
            ],
            {"base_depth": 10.0},
        )
        out = compile_ir(doc)
        import_block = out.split("from build123d import")[1].split(")")[0]
        self.assertIn("Line", import_block)
        self.assertIn("sweep", import_block)

    def test_sweep_emits_sketch_and_path(self):
        doc = self._minimal_doc(
            [
                {"id": "b", "type": "extrude_add",
                 "sketch": {"plane": "XY",
                   "entities": [{"type": "center_rectangle",
                     "center": [0, 0], "size": [10, 10]}]},
                 "depth": "base_depth", "direction": "+Z"},
                {"id": "t", "type": "sweep",
                 "profile": {"sketch": {"plane": "XY",
                   "entities": [{"type": "circle",
                     "center": [0, 0], "diameter": "r"}]}},
                 "path": {"start": ["x1", 0, "z1"],
                          "end": ["x2", 0, "z2"]}},
            ],
            {"base_depth": 10.0, "r": 5.0,
             "x1": 0.0, "z1": 0.0, "x2": 100.0, "z2": 50.0},
        )
        out = compile_ir(doc)
        self.assertIn("path = Line([params['x1'], 0, params['z1']],"
                      " [params['x2'], 0, params['z2']])", out)
        self.assertIn("sweep(path=path)", out)
        self.assertIn("with BuildSketch(Plane.XY):", out)

    def test_sweep_without_extrude_add_raises(self):
        doc = self._minimal_doc(
            [
                {"id": "t", "type": "sweep",
                 "profile": {"sketch": {"plane": "XY",
                   "entities": [{"type": "circle",
                     "center": [0, 0], "diameter": "r"}]}},
                 "path": {"start": ["x1", 0, "z1"],
                          "end": ["x2", 0, "z2"]}},
            ],
            {"r": 5.0, "x1": 0.0, "z1": 0.0,
             "x2": 100.0, "z2": 50.0},
        )
        with self.assertRaises(ValueError) as ctx:
            compile_ir(doc)
        msg = str(ctx.exception)
        # validator reports unused params first, then compile_ir
        # checks extrude_add count.  We just assert it fails.
        self.assertTrue(
            "unused_parameter" in msg or "extrude_add" in msg,
            f"unexpected error: {msg}",
        )

    def test_multiple_sweeps(self):
        doc = self._minimal_doc(
            [
                {"id": "b", "type": "extrude_add",
                 "sketch": {"plane": "XY",
                   "entities": [{"type": "center_rectangle",
                     "center": [0, 0], "size": [10, 10]}]},
                 "depth": "base_depth", "direction": "+Z"},
                {"id": "t1", "type": "sweep",
                 "profile": {"sketch": {"plane": "XY",
                   "entities": [{"type": "circle",
                     "center": [0, 0], "diameter": "r"}]}},
                 "path": {"start": ["x1", 0, "z1"],
                          "end": ["x2", 0, "z2"]}},
                {"id": "t2", "type": "sweep",
                 "profile": {"sketch": {"plane": "XY",
                   "entities": [{"type": "circle",
                     "center": [0, 0], "diameter": "r"}]}},
                 "path": {"start": ["x2", 0, "z2"],
                          "end": ["x2", 0, "z2"]}},
            ],
            {"base_depth": 10.0, "r": 5.0,
             "x1": 0.0, "z1": 0.0, "x2": 100.0, "z2": 50.0},
        )
        out = compile_ir(doc)
        self.assertEqual(out.count("sweep(path=path)"), 2)


if __name__ == "__main__":
    unittest.main()
