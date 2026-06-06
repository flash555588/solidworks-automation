"""Tests for the core algorithm modules: schema / planner / validator /
primitives / solidworks_compiler facade.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))

from cad_ai import (  # type: ignore
    ir_validate, planner, primitives, projection_validator,
    schema, solidworks_compiler, sw_compile,
)


class SchemaDataclassTests(unittest.TestCase):
    def test_round_trip(self):
        cad = schema.CADIR(name="demo", units="mm")
        cad.add_parameter("width", 10.0)
        cad.add_feature(schema.CADFeature(
            id="base", type="extrude_add",
            parameters={"depth": "width", "direction": "+Z"},
        ))
        doc = cad.to_dict()
        self.assertEqual(doc["schema"], "cad_ir.v0")
        self.assertEqual(doc["parameters"]["width"], 10.0)
        rebuilt = schema.CADIR.from_dict(doc)
        self.assertEqual(rebuilt.name, "demo")
        self.assertEqual(len(rebuilt.features), 1)
        self.assertEqual(rebuilt.features[0].id, "base")

    def test_from_dict_skips_malformed(self):
        doc = {
            "schema": "cad_ir.v0",
            "units": "mm",
            "document": {"type": "part", "name": "x"},
            "coordinate_system": {"origin": "p", "up_axis": "Z", "front_axis": "Y"},
            "parameters": {},
            "features": [
                {"id": "good", "type": "extrude_add", "depth": 1.0},
                {"id": "no_type", "depth": 1.0},
                {"type": "extrude_add", "depth": 1.0},  # no id
                "not a dict",
            ],
        }
        cad = schema.CADIR.from_dict(doc)
        self.assertEqual([f.id for f in cad.features], ["good"])


class PlannerTests(unittest.TestCase):
    def test_ordering(self):
        cad = schema.CADIR(name="x")
        cad.add_feature(schema.CADFeature(id="fillet", type="fillet", parameters={}))
        cad.add_feature(schema.CADFeature(id="base", type="extrude_add", parameters={}))
        cad.add_feature(schema.CADFeature(id="cut", type="extrude_cut", parameters={}))
        cad.add_feature(schema.CADFeature(id="pat", type="pattern", parameters={}))
        ordered = planner.plan_feature_sequence(cad)
        ids = [f.id for f in ordered]
        # base, then cut, then fillet, then pattern.
        self.assertEqual(ids, ["base", "cut", "fillet", "pat"])

    def test_stable_within_bucket(self):
        cad = schema.CADIR(name="x")
        cad.add_feature(schema.CADFeature(id="a", type="extrude_add", parameters={}))
        cad.add_feature(schema.CADFeature(id="b", type="extrude_add", parameters={}))
        ordered = planner.plan_feature_sequence(cad)
        self.assertEqual([f.id for f in ordered], ["a", "b"])

    def test_unknown_type_preserved(self):
        cad = schema.CADIR(name="x")
        cad.add_feature(schema.CADFeature(id="z", type="custom_thing", parameters={}))
        ordered = planner.plan_feature_sequence(cad)
        self.assertEqual([f.id for f in ordered], ["z"])


class ProjectionValidatorTests(unittest.TestCase):
    def _doc(self, **kwargs):
        base = {
            "schema": "cad_ir.v0",
            "units": "mm",
            "document": {"type": "part", "name": "x"},
            "coordinate_system": {"origin": "p", "up_axis": "Z", "front_axis": "Y"},
            "parameters": {},
            "features": [],
        }
        base.update(kwargs)
        return base
    def test_negative_parameters_allowed_for_position(self):
        # Geometric coordinates are allowed to be negative
        # (e.g. the rear axle is behind the bottom bracket);
        # only *dimensions* must be positive.  The projection
        # validator therefore does not flag non-positive
        # parameters.
        doc = self._doc(parameters={"width": -5, "radius": 10})
        result = projection_validator.validate_projection(doc)
        self.assertTrue(result["ok"], result)
    def test_unknown_target(self):
        doc = self._doc(features=[
            {"id": "f1", "type": "extrude_cut", "target": "missing",
             "sketch": {"plane": "XY", "entities": []},
             "depth": 1.0, "direction": "+Z"},
        ])
        result = projection_validator.validate_projection(doc)
        self.assertFalse(result["ok"])
        self.assertTrue(any(e["code"] == "unknown_reference" for e in result["errors"]))

    def test_clean_document_passes(self):
        doc = self._doc(parameters={"width": 10}, features=[
            {"id": "f1", "type": "extrude_add",
             "sketch": {"plane": "XY",
                        "entities": [{"type": "circle", "center": [0, 0],
                                       "diameter": 5}]},
             "depth": 10.0, "direction": "+Z"},
        ])
        result = projection_validator.validate_projection(doc)
        self.assertTrue(result["ok"], result)


class PrimitivesTests(unittest.TestCase):
    def test_bicycle_skeleton_compiles(self):
        cad = primitives.bicycle_skeleton()
        # Ensure parameters and features line up.
        self.assertIn("wheel_radius", cad.parameters)
        self.assertTrue(any(f.id == "front_wheel_outer" for f in cad.features))
        self.assertTrue(any(f.id == "down_tube" for f in cad.features))
        doc = cad.to_dict()
        v = ir_validate.validate_ir(doc)
        self.assertTrue(v["ok"], v)
        # And the SW-side compiler must accept it.
        stream = sw_compile.compile_sw(doc)
        op_ids = [op["op"] for op in stream["operations"]]
        self.assertIn("extrude", op_ids)
        self.assertIn("extrude_cut", op_ids)

    def test_tube_axis_aligned(self):
        f = primitives.tube(
            "stub", start=("0", "0"), end=("100", "0"),
        )
        # The length should be 100-0 = "100-0" -- a string the
        # sw_compile resolver will fall back to a literal.
        self.assertEqual(f.parameters["depth"], "100-0")

    def test_wheel_pair_returns_four(self):
        wheels = primitives.wheel_pair(
            front_axle=("a", "0"), rear_axle=("b", "0"),
        )
        self.assertEqual(len(wheels), 4)
        self.assertEqual([w.id for w in wheels],
                         ["front_wheel_outer", "front_wheel_inner",
                          "rear_wheel_outer", "rear_wheel_inner"])


class CompilerFacadeTests(unittest.TestCase):
    def test_compile_only_succeeds(self):
        cad = primitives.bicycle_skeleton()
        result = solidworks_compiler.compile_only(cad.to_dict())
        self.assertTrue(result["ok"], result)
        self.assertIn("operations", result["stream"])

    def test_compile_only_fails_on_bad_ir(self):
        bad = {"schema": "wrong"}
        result = solidworks_compiler.compile_only(bad)
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
