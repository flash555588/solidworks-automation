"""Contract tests for cad_ai.sw_compile.

The contract is documented in
`contracts/cad_ir_to_sw_contract.md`.  These tests verify that
the contract is honoured by `sw_compile.compile_sw` and that the
`mock_sw` reference backend produces a STEP that matches the
direct cad_ai path within the IR's `tolerance_mm`.

Run with:

    python -m unittest skills/cad_ai/tests/test_sw_compile.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))

from cad_ai import sw_compile  # noqa: E402

# Operation whitelist per `contracts/cad_ir_to_sw_contract.md`.
ALLOWED_OPS = {
    "new_part",
    "select_plane",
    "select_face",
    "sketch_begin",
    "sketch_end",
    "sketch_rectangle",
    "sketch_polygon",
    "sketch_circle",
    "sketch_circle_pattern",
    "extrude",
    "extrude_cut",
    "fillet",
    "chamfer",
}

EXAMPLES_DIR = _HERE.parent / "examples"


def _load(name):
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _ops(stream):
    return [op["op"] for op in stream["operations"]]


class SwCompileContractTests(unittest.TestCase):
    def test_stream_shape(self):
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        self.assertEqual(stream["schema"], "sw_instructions.v0")
        self.assertEqual(stream["document"], "part")
        self.assertIn("operations", stream)
        self.assertIsInstance(stream["operations"], list)
        self.assertGreater(len(stream["operations"]), 0)
        # Every operation must be in the whitelist.
        for op in stream["operations"]:
            self.assertIn(op["op"], ALLOWED_OPS,
                           msg=f"unknown operation: {op!r}")

    def test_mounting_plate_starts_with_new_part(self):
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        self.assertEqual(stream["operations"][0]["op"], "new_part")
        self.assertEqual(stream["operations"][0]["name"], "mounting_plate")

    def test_mounting_plate_emits_one_extrude_for_base(self):
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        extrudes = [op for op in stream["operations"]
                     if op["op"] == "extrude"]
        self.assertEqual(len(extrudes), 1)
        # The base extrude references the plate dimensions.
        self.assertEqual(extrudes[0]["depth"], 0.01)
        self.assertEqual(extrudes[0]["direction"], "+Z")

    def test_mounting_plate_emits_one_extrude_cut_per_hole(self):
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        cuts = [op for op in stream["operations"]
                 if op["op"] == "extrude_cut"]
        self.assertEqual(len(cuts), 4)
        for c in cuts:
            self.assertEqual(c["depth"], "through")

    def test_extrude_carries_feature_id(self):
        # v0.2: the base extrude_add forwards its IR id as
        # feature_id so the SW host can build a
        # feature_id -> feature object map.  A subtractive op
        # with a target then resolves the body by id.
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        extrudes = [op for op in stream["operations"]
                     if op["op"] == "extrude"]
        self.assertEqual(len(extrudes), 1)
        self.assertEqual(extrudes[0]["feature_id"], "base_plate")

    def test_extrude_cut_carries_target(self):
        # v0.2: every extrude_cut must forward the IR
        # target field so the SW host can select the
        # targeted body before the cut.  mounting_plate has
        # four hole_through features; sw_compile emits them
        # as extrude_cut ops with target == base_plate.
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        cuts = [op for op in stream["operations"]
                 if op["op"] == "extrude_cut"]
        self.assertEqual(len(cuts), 4)
        for c in cuts:
            self.assertEqual(c["target"], "base_plate")

    def test_plates_with_fillet_emit_fillet_op(self):
        ir = _load("plate_with_fillet.ir.json")
        stream = sw_compile.compile_sw(ir)
        fillets = [op for op in stream["operations"]
                    if op["op"] == "fillet"]
        self.assertEqual(len(fillets), 1)
    def test_numeric_values_are_resolved(self):
        """The instruction stream must carry resolved numbers for
        numeric fields, not parameter references, so a SOLIDWORKS
        backend has no dependency on the cad_ai parameter system.
        String fields that are enums (operation name, plane name,
        direction, selector kind, document name) are allowed to
        remain strings.  We only check fields whose value in the
        IR is a number or a parameter reference.
        """
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        # These operation-field pairs must resolve to numbers.
        must_resolve = (
            ("extrude", "depth"),
            ("fillet", "radius"),
            ("chamfer", "size"),
            ("sketch_rectangle", "size"),
            ("sketch_circle", "diameter"),
        )
        for op in stream["operations"]:
            for kind, field in must_resolve:
                if op["op"] == kind and field in op:
                    self.assertNotIsInstance(
                        op[field], str,
                        msg=f"unresolved {field} in {op!r}",
                    )


    def test_join_bodies_emits_boolean_union(self):
        # v0.2: a join_bodies IR feature must produce a
        # boolean_union op at the end of the stream.
        ir = {
            "schema": "cad_ir.v0",
            "units": "mm",
            "document": {"type": "part", "name": "multi"},
            "coordinate_system": {
                "origin": "part_center",
                "up_axis": "Z",
                "front_axis": "Y",
            },
            "parameters": {},
            "features": [
                {"id": "base", "type": "extrude_add",
                 "sketch": {"plane": "XY",
                   "entities": [{"type": "center_rectangle",
                     "center": [0, 0], "size": [10, 10]}]},
                 "depth": 5.0, "direction": "+Z"},
                {"id": "join", "type": "join_bodies"},
            ],
        }
        stream = sw_compile.compile_sw(ir)
        unions = [op for op in stream["operations"]
                  if op["op"] == "boolean_union"]
        self.assertEqual(len(unions), 1)
        self.assertTrue(unions[0].get("all"))


    def test_revolve_emits_revolve_op(self):
        ir = {
            'schema': 'cad_ir.v0',
            'units': 'mm',
            'document': {'type': 'part', 'name': 'rev'},
            'coordinate_system': {'origin': 'part_center', 'up_axis': 'Z', 'front_axis': 'Y'},
            'parameters': {'angle': 180},
            'features': [
                {'id': 'base', 'type': 'extrude_add',
                 'sketch': {'plane': 'XY',
                   'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'size': [10, 10]}]},
                 'depth': 5.0, 'direction': '+Z'},
                {'id': 'rev1', 'type': 'revolve',
                 'sketch': {'plane': 'XY',
                   'entities': [{'type': 'circle', 'center': [0, 0], 'diameter': 5}]},
                 'angle': 'angle', 'axis': '+Z'},
            ],
        }
        stream = sw_compile.compile_sw(ir)
        rev_ops = [op for op in stream['operations'] if op['op'] == 'revolve']
        self.assertEqual(len(rev_ops), 1)
        self.assertEqual(rev_ops[0]['angle'], 180)
        self.assertEqual(rev_ops[0]['axis'], '+Z')

    def test_mirror_emits_mirror_op(self):
        ir = {
            'schema': 'cad_ir.v0',
            'units': 'mm',
            'document': {'type': 'part', 'name': 'mir'},
            'coordinate_system': {'origin': 'part_center', 'up_axis': 'Z', 'front_axis': 'Y'},
            'parameters': {},
            'features': [
                {'id': 'base', 'type': 'extrude_add',
                 'sketch': {'plane': 'XY',
                   'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'size': [10, 10]}]},
                 'depth': 5.0, 'direction': '+Z'},
                {'id': 'mir1', 'type': 'mirror',
                 'features': ['base'], 'plane': 'YZ'},
            ],
        }
        stream = sw_compile.compile_sw(ir)
        mir_ops = [op for op in stream['operations'] if op['op'] == 'mirror']
        self.assertEqual(len(mir_ops), 1)
        self.assertEqual(mir_ops[0]['features'], ['base'])
        self.assertEqual(mir_ops[0]['plane'], 'YZ')

    def test_linear_pattern_emits_linear_pattern_op(self):
        ir = {
            'schema': 'cad_ir.v0',
            'units': 'mm',
            'document': {'type': 'part', 'name': 'pat'},
            'coordinate_system': {'origin': 'part_center', 'up_axis': 'Z', 'front_axis': 'Y'},
            'parameters': {'spacing': 20},
            'features': [
                {'id': 'base', 'type': 'extrude_add',
                 'sketch': {'plane': 'XY',
                   'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'size': [10, 10]}]},
                 'depth': 5.0, 'direction': '+Z'},
                {'id': 'hole', 'type': 'hole_through',
                 'diameter': 3, 'axis': 'Z', 'target': 'base', 'position': [0, 0]},
                {'id': 'pat1', 'type': 'linear_pattern',
                 'features': ['hole'], 'direction': 'X', 'spacing': 'spacing', 'count': 3},
            ],
        }
        stream = sw_compile.compile_sw(ir)
        pat_ops = [op for op in stream['operations'] if op['op'] == 'linear_pattern']
        self.assertEqual(len(pat_ops), 1)
        self.assertEqual(pat_ops[0]['count'], 3)
        self.assertEqual(pat_ops[0]['spacing'], 0.02)

    def test_shell_emits_shell_op(self):
        ir = {
            'schema': 'cad_ir.v0',
            'units': 'mm',
            'document': {'type': 'part', 'name': 'shell'},
            'coordinate_system': {'origin': 'part_center', 'up_axis': 'Z', 'front_axis': 'Y'},
            'parameters': {'t': 2},
            'features': [
                {'id': 'base', 'type': 'extrude_add',
                 'sketch': {'plane': 'XY',
                   'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'size': [10, 10]}]},
                 'depth': 5.0, 'direction': '+Z'},
                {'id': 'sh1', 'type': 'shell',
                 'thickness': 't', 'faces': []},
            ],
        }
        stream = sw_compile.compile_sw(ir)
        sh_ops = [op for op in stream['operations'] if op['op'] == 'shell']
        self.assertEqual(len(sh_ops), 1)
        self.assertEqual(sh_ops[0]['thickness'], 0.002)

    def test_join_bodies_absent_when_not_present(self):
        # v0.2: without a join_bodies feature, no boolean_union op.
        ir = _load("mounting_plate.ir.json")
        stream = sw_compile.compile_sw(ir)
        unions = [op for op in stream["operations"]
                  if op["op"] == "boolean_union"]
        self.assertEqual(len(unions), 0)


if __name__ == "__main__":
    unittest.main()
