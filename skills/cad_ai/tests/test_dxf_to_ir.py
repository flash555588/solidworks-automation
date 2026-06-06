"""Unit tests for cad_ai.dxf_to_ir.

The tests build their own DXF inputs in-memory (using the same
ezdxf primitive calls as `examples/mounting_plate_three_views/generate.py`),
so they are self-contained and do not depend on a checked-in DXF
file at a particular path.

Run with:

    python -m unittest skills/cad_ai/tests/test_dxf_to_ir.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Make the local cad_ai package importable.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))

import ezdxf  # noqa: E402

from cad_ai.dxf_to_ir import DXFReaderError, read_three_views  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers to build a 3-view DXF set in a temp directory.
# ---------------------------------------------------------------------------

LENGTH = 100.0
WIDTH = 60.0
THICKNESS = 10.0
HOLE_R = 3.0
HOLE_CENTRES = [(-40.0, -20.0), (40.0, -20.0),
                (-40.0, 20.0), (40.0, 20.0)]


def _rect(doc, x_min, y_min, x_max, y_max):
    msp = doc.modelspace()
    corners = [(x_min, y_min), (x_max, y_min),
                (x_max, y_max), (x_min, y_max)]
    for i in range(4):
        msp.add_line(start=corners[i], end=corners[(i + 1) % 4])


def _circles(doc, centres):
    msp = doc.modelspace()
    for (cx, cy) in centres:
        msp.add_circle(center=(cx, cy), radius=HOLE_R)


def _write_views(tmp: Path, *, front_w=None, top_w=None, right_w=None,
                  front_circles=None, top_circles=None, right_circles=None,
                  front_extra=None, top_extra=None, right_extra=None):
    """Write three DXF files into `tmp` and return their paths.

    `front_w` / `top_w` / `right_w` override the width of the
    base rectangle in the corresponding view, used to test
    cross-view disagreement.

    `*_circles` overrides the per-view list of hole centres; if
    None, the default `HOLE_CENTRES` is used.

    `*_extra` is an optional callable that adds extra entities to
    the view; used to inject unsupported types like ARC.
    """
    if front_circles is None:
        front_circles = HOLE_CENTRES
    if top_circles is None:
        top_circles = HOLE_CENTRES
    if right_circles is None:
        right_circles = HOLE_CENTRES
    if front_w is None:
        front_w = LENGTH
    if top_w is None:
        top_w = LENGTH
    if right_w is None:
        right_w = WIDTH

    # Front
    doc = ezdxf.new()
    _rect(doc, -front_w / 2, -THICKNESS / 2, +front_w / 2, +THICKNESS / 2)
    # For the front view we want circles at (hx, 0) since Z is centred.
    _circles(doc, [(cx, 0.0) for (cx, cy) in front_circles])
    if front_extra is not None:
        front_extra(doc)
    front_path = tmp / "front.dxf"
    doc.saveas(str(front_path))

    # Top
    doc = ezdxf.new()
    _rect(doc, -top_w / 2, -WIDTH / 2, +top_w / 2, +WIDTH / 2)
    _circles(doc, top_circles)
    if top_extra is not None:
        top_extra(doc)
    top_path = tmp / "top.dxf"
    doc.saveas(str(top_path))

    # Right
    doc = ezdxf.new()
    _rect(doc, -right_w / 2, -THICKNESS / 2, +right_w / 2, +THICKNESS / 2)
    # For the right view we want circles at (hy, 0) since Z is centred.
    _circles(doc, [(cy, 0.0) for (cx, cy) in right_circles])
    if right_extra is not None:
        right_extra(doc)
    right_path = tmp / "right.dxf"
    doc.saveas(str(right_path))

    return front_path, top_path, right_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ReadThreeViewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_happy_path(self):
        front, top, right = _write_views(self.tmp)
        ir = read_three_views(str(front), str(top), str(right))
        self.assertEqual(ir["schema"], "cad_ir.v0")
        self.assertEqual(ir["units"], "mm")
        self.assertEqual(ir["document"]["type"], "part")
        self.assertEqual(ir["parameters"]["plate_length"], LENGTH)
        self.assertEqual(ir["parameters"]["plate_width"], WIDTH)
        self.assertEqual(ir["parameters"]["plate_thickness"], THICKNESS)
        # Four holes, diameters 2 * HOLE_R = 6.
        self.assertEqual(
            sum(1 for k in ir["parameters"]
                if k.startswith("hole_") and k.endswith("_diameter")),
            4,
        )
        for i in range(4):
            self.assertEqual(ir["parameters"][f"hole_{i}_diameter"], 2 * HOLE_R)
        # Acceptance block reflects the geometry.
        self.assertEqual(ir["acceptance"]["bbox"], [LENGTH, WIDTH, THICKNESS])
        self.assertIn("single_solid", ir["acceptance"]["must_have"])

    def test_rejects_circle_count_mismatch(self):
        # Front and right have 4 holes, top has only 3.
        top_circles = HOLE_CENTRES[:3]
        front, top, right = _write_views(
            self.tmp, top_circles=top_circles)
        with self.assertRaises(DXFReaderError) as ctx:
            read_three_views(str(front), str(top), str(right))
        self.assertIn("same number of CIRCLE", str(ctx.exception))

    def test_rejects_view_boundary_mismatch(self):
        # Front says the part is 80 long; top says it is 100 long.
        front, top, right = _write_views(self.tmp, top_w=LENGTH,
                                          front_w=80.0)
        with self.assertRaises(DXFReaderError) as ctx:
            read_three_views(str(front), str(top), str(right))
        self.assertIn("disagree on x bounds", str(ctx.exception))

    def test_rejects_unsupported_entity(self):
        # Inject an ARC into the front view.
        def add_arc(doc):
            doc.modelspace().add_arc(
                center=(0, 0), radius=5.0,
                start_angle=0, end_angle=90,
            )
        front, top, right = _write_views(self.tmp, front_extra=add_arc)
        with self.assertRaises(DXFReaderError) as ctx:
            read_three_views(str(front), str(top), str(right))
        self.assertIn("unsupported entity", str(ctx.exception))

    def test_hole_radius_mismatch_rejected(self):
        # Top holes have a different radius than front/right.
        doc_front = ezdxf.new()
        _rect(doc_front, -LENGTH / 2, -THICKNESS / 2,
              +LENGTH / 2, +THICKNESS / 2)
        _circles(doc_front, [(cx, 0.0) for (cx, cy) in HOLE_CENTRES])
        front = self.tmp / "front.dxf"
        doc_front.saveas(str(front))

        doc_top = ezdxf.new()
        _rect(doc_top, -LENGTH / 2, -WIDTH / 2, +LENGTH / 2, +WIDTH / 2)
        msp = doc_top.modelspace()
        # Same centres, different radii.
        for (cx, cy) in HOLE_CENTRES:
            msp.add_circle(center=(cx, cy), radius=HOLE_R + 1.0)
        top = self.tmp / "top.dxf"
        doc_top.saveas(str(top))

        doc_right = ezdxf.new()
        _rect(doc_right, -WIDTH / 2, -THICKNESS / 2,
              +WIDTH / 2, +THICKNESS / 2)
        _circles(doc_right, [(cy, 0.0) for (cx, cy) in HOLE_CENTRES])
        right = self.tmp / "right.dxf"
        doc_right.saveas(str(right))

        with self.assertRaises(DXFReaderError) as ctx:
            read_three_views(str(front), str(top), str(right))
        self.assertIn("radius mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
