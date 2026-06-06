"""Unit tests for cad_ai/ir_validate.py.

The tests are stdlib-only.  They exercise the validator's contract:
acceptance on a valid IR, rejection on bad feature types, and
rejection of forward target references.

Run with:

    python -m unittest skills/cad_ai/tests/test_ir_validate.py

Or:

    cd skills/cad_ai/tests
    python -m unittest test_ir_validate
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Make the `cad_ai` package importable when running this file from any cwd.
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from cad_ai import ir_validate  # noqa: E402


# ---------------------------------------------------------------------------
# Reusable IR fragments
# ---------------------------------------------------------------------------

VALID_DOC = {
    "schema": "cad_ir.v0",
    "units": "mm",
    "document": {"type": "part", "name": "test_part"},
    "coordinate_system": {
        "origin": "part_center",
        "up_axis": "Z",
        "front_axis": "Y",
    },
    "parameters": {
        "length": 10.0,
        "width": 5.0,
        "height": 3.0,
    },
    "features": [
        {
            "id": "base",
            "type": "extrude_add",
            "sketch": {
                "plane": "XY",
                "entities": [
                    {
                        "type": "center_rectangle",
                        "center": [0, 0],
                        "size": ["length", "width"],
                    },
                ],
            },
            "depth": "height",
            "direction": "+Z",
        },
    ],
}


def _make_bad_feature_type_doc():
    doc = json.loads(json.dumps(VALID_DOC))
    doc["features"][0]["type"] = "explode_add"  # not in the whitelist
    return doc


def _make_forward_target_ref_doc():
    doc = json.loads(json.dumps(VALID_DOC))
    doc["features"].append({
        "id": "hole",
        "type": "hole_through",
        "target": "no_such_feature",  # forward ref that does not exist
        "diameter": 1.0,
        "axis": "Z",
        "position": [0, 0],
    })
    return doc


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class ValidateIRTests(unittest.TestCase):
    def test_valid_ir_returns_ok(self):
        result = ir_validate.validate_ir(VALID_DOC)
        self.assertTrue(result["ok"], msg=f"errors: {result['errors']}")
        self.assertEqual(result["errors"], [])

    def test_unknown_feature_type_is_rejected(self):
        result = ir_validate.validate_ir(_make_bad_feature_type_doc())
        self.assertFalse(result["ok"])
        # At least one error must point at the offending type field.
        bad = [e for e in result["errors"]
                if e["path"] == "$.features[0].type"
                and e["code"] == "unsupported_feature_type"]
        self.assertEqual(len(bad), 1,
                          msg=f"expected one unsupported_feature_type error at "
                              f"$.features[0].type, got {result['errors']}")

    def test_unknown_target_ref_is_rejected(self):
        result = ir_validate.validate_ir(_make_forward_target_ref_doc())
        self.assertFalse(result["ok"])
        # The bad target is on the second feature.
        bad = [e for e in result["errors"]
                if e["path"] == "$.features[1].target"
                and e["code"] == "unknown_ref"]
        self.assertEqual(len(bad), 1,
                          msg=f"expected one unknown_ref error at "
                              f"$.features[1].target, got {result['errors']}")


# ---------------------------------------------------------------------------
# Examples-on-disk tests: both shipped examples must validate cleanly.
# ---------------------------------------------------------------------------


class ExampleIRTests(unittest.TestCase):
    def setUp(self):
        self.examples_dir = _HERE.parent / "examples"

    def _load(self, name):
        return json.loads((self.examples_dir / name).read_text(encoding="utf-8"))

    def test_mounting_plate_v0_validates(self):
        doc = self._load("mounting_plate.ir.json")
        result = ir_validate.validate_ir(doc)
        self.assertTrue(result["ok"],
                         msg=f"errors: {result['errors']}")

    def test_plate_with_fillet_v1_validates(self):
        doc = self._load("plate_with_fillet.ir.json")
        result = ir_validate.validate_ir(doc)
        self.assertTrue(result["ok"],
                         msg=f"errors: {result['errors']}")


if __name__ == "__main__":
    unittest.main()
