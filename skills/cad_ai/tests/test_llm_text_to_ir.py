"""Unit tests for cad_ai.llm.text_to_ir.

The LLM is mocked by patching `cadpy.llm.client.chat`.  These tests
exercise the JSON extraction, the validation retry loop, and the
error classification.  They do not require a live LLM.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))

# Import the module, not the function: the package's __init__
from cad_ai.llm import errors as llm_errors  # noqa: E402
import cad_ai.llm.text_to_ir as llm_text_to_ir  # noqa: E402
import cad_ai.llm.text_to_ir as llm_text_to_ir  # noqa: E402


# A minimal valid IR that the test can post back from the mocked LLM.
VALID_IR = {
    "schema": "cad_ir.v0",
    "units": "mm",
    "document": {"type": "part", "name": "test"},
    "coordinate_system": {
        "origin": "part_center", "up_axis": "Z", "front_axis": "Y",
    },
    "parameters": {"length": 10.0, "width": 5.0, "height": 3.0},
    "features": [
        {
            "id": "base",
            "type": "extrude_add",
            "sketch": {
                "plane": "XY",
                "entities": [{
                    "type": "center_rectangle",
                    "center": [0, 0],
                    "size": ["length", "width"],
                }],
            },
            "depth": "height",
            "direction": "+Z",
        },
    ],
}


def _patch_chat(responses):
    """Patch `cadpy.llm.client.chat` to return canned responses in order."""
    iter_responses = iter(responses)

    def fake_chat(messages, **_):
        return next(iter_responses)

    return mock.patch.object(llm_text_to_ir, "chat", side_effect=fake_chat)


class ExtractJSONTests(unittest.TestCase):
    def test_extracts_raw_object(self):
        text = json.dumps(VALID_IR)
        self.assertEqual(llm_text_to_ir._extract_json(text), VALID_IR)

    def test_extracts_fenced_object(self):
        text = "Here you go:\n```json\n" + json.dumps(VALID_IR) + "\n```\n"
        self.assertEqual(llm_text_to_ir._extract_json(text), VALID_IR)

    def test_raises_on_garbage(self):
        with self.assertRaises(llm_errors.LLMJSONError):
            llm_text_to_ir._extract_json("not json at all")


class RetryLoopTests(unittest.TestCase):
    def test_first_response_validates(self):
        with _patch_chat([json.dumps(VALID_IR)]) as m:
            ir = llm_text_to_ir.text_to_ir("ignored", max_retries=2)
        self.assertEqual(ir, VALID_IR)
        self.assertEqual(m.call_count, 1)

    def test_retries_on_validation_failure_then_succeeds(self):
        bad = json.dumps(VALID_IR)
        # First response is missing a required field.  We simulate by
        # dropping `parameters` and putting it back in the second call.
        bad_ir = {k: v for k, v in VALID_IR.items() if k != "parameters"}
        # Validator requires parameters; missing_field is reported.
        # The retry loop will see validation errors and call again.
        with _patch_chat([json.dumps(bad_ir), json.dumps(VALID_IR)]) as m:
            ir = llm_text_to_ir.text_to_ir("ignored", max_retries=2)
        self.assertEqual(ir, VALID_IR)
        self.assertEqual(m.call_count, 2)

    def test_raises_validation_error_after_exhausted_retries(self):
        bad_ir = {k: v for k, v in VALID_IR.items() if k != "parameters"}
        with _patch_chat([json.dumps(bad_ir)] * 3) as m:
            with self.assertRaises(llm_errors.LLMValidationError) as ctx:
                llm_text_to_ir.text_to_ir("ignored", max_retries=2)
        self.assertEqual(m.call_count, 3)
        self.assertGreaterEqual(len(ctx.exception.errors), 1)


if __name__ == "__main__":
    unittest.main()
