"""Contract test for solidworks_com.compiler.cad_ir_to_sw.

The translator is verified against a mock ModelDoc that records
every call.  The expected call sequence is derived from the
mounting_plate.ir.json example: 1 base extrude + 4 hole cuts.

This test does NOT require a SOLIDWORKS install.  The mock
provides the methods the translator dispatches to.

Run with::

    python -m unittest tests/test_cad_ir_to_sw.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Make both the repo root (for solidworks_com) and cad_ai scripts
# (for sw_compile) importable from this test file.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "skills" / "cad_ai" / "scripts"))


class _EdgeWithCentroid:
    # A v0.2 mock edge that exposes the ``centroid`` attribute
    # the translator reads first.  ``payload`` is the wrapped
    # value the test asserts on (the real SW Edge is opaque).
    def __init__(self, payload, centroid):
        self.payload = payload
        self.centroid = centroid


class _MockSketch:
    """Records the entity calls made through the sketch context."""

    def __init__(self) -> None:
        self.calls = []

    def corner_rectangle(self, x1, y1, x2, y2):
        self.calls.append(("rectangle", (x1, y1, x2, y2)))

    def circle(self, cx, cy, r):
        self.calls.append(("circle", (cx, cy, r)))

    def polygon(self, cx, cy, vx, vy, sides, inscribed):
        self.calls.append(("polygon", (cx, cy, vx, vy, sides, inscribed)))

    def line(self, x1, y1, z1, x2, y2, z2):
        self.calls.append(("line_3d", (x1, y1, z1, x2, y2, z2)))


class _MockFeatures:
    def __init__(self) -> None:
        self.extrude_blind_calls = []
        self.cut_blind_calls = []
        self.fillet_calls = []
        self.chamfer_calls = []
        self.bool_union_calls = []

    def extrude_blind(self, depth, *, merge, reverse):
        self.extrude_blind_calls.append((depth, merge, reverse))
        return ("feature", len(self.extrude_blind_calls))

    def cut_blind(self, depth, *, reverse, normal_cut):
        self.cut_blind_calls.append((depth, reverse, normal_cut))
        return ("feature", -len(self.cut_blind_calls))

    def fillet_selected(self, radius, *, options=0):
        self.fillet_calls.append((radius, options))
        return ("fillet",)

    def chamfer_selected(self, distance, *, chamfer_type, options=0,
                         angle=0.0, other_distance=0.0,
                         vertex_distance_1=0.0, vertex_distance_2=0.0,
                         vertex_distance_3=0.0):
        self.chamfer_calls.append((distance, chamfer_type, options))
        return ("chamfer",)

    def bool_union(self, body1, body2):
        self.bool_union_calls.append((body1, body2))
        return ("union_feature", len(self.bool_union_calls))



    def revolve(self, *, angle=None, cut=False, reverse=False, merge=True):
        self.revolve_calls = getattr(self, 'revolve_calls', [])
        self.revolve_calls.append((angle, cut, reverse, merge))
        return ('revolve', len(self.revolve_calls))

    def loft_boss(self, *, closed=False, merge=True, **kw):
        self.loft_boss_calls = getattr(self, 'loft_boss_calls', [])
        self.loft_boss_calls.append((closed, merge))
        return ('loft_boss', len(self.loft_boss_calls))

    def loft_cut(self, *, merge=True, **kw):
        self.loft_cut_calls = getattr(self, 'loft_cut_calls', [])
        self.loft_cut_calls.append((merge,))
        return ('loft_cut', len(self.loft_cut_calls))

    def mirror_selected(self, *, merge=True):
        self.mirror_calls = getattr(self, 'mirror_calls', [])
        self.mirror_calls.append((merge,))
        return ('mirror', len(self.mirror_calls))

    def linear_pattern_selected(self, count, spacing, *, merge=True):
        self.linear_pattern_calls = getattr(self, 'linear_pattern_calls', [])
        self.linear_pattern_calls.append((count, spacing, merge))
        return ('linear_pattern', len(self.linear_pattern_calls))

    def circular_pattern_selected(self, count, angle, *, merge=True):
        self.circular_pattern_calls = getattr(self, 'circular_pattern_calls', [])
        self.circular_pattern_calls.append((count, angle, merge))
        return ('circular_pattern', len(self.circular_pattern_calls))

    def shell_selected(self, thickness, *, remove_faces=True):
        self.shell_calls = getattr(self, 'shell_calls', [])
        self.shell_calls.append((thickness, remove_faces))
        return ('shell', len(self.shell_calls))

    def draft_selected(self, angle, *, draft_type=0):
        self.draft_calls = getattr(self, 'draft_calls', [])
        self.draft_calls.append((angle, draft_type))
        return ('draft', len(self.draft_calls))

    def loft_surface(self, *, closed=False, **kw):
        self.loft_surface_calls = getattr(self, 'loft_surface_calls', [])
        self.loft_surface_calls.append((closed,))
        return ('loft_surface', len(self.loft_surface_calls))

    def thicken_selected(self, thickness, *, direction=0, fill_volume=False, merge=True):
        self.thicken_calls = getattr(self, 'thicken_calls', [])
        self.thicken_calls.append((thickness, direction, merge))
        return ('thicken', len(self.thicken_calls))

    def fill_surface_selected(self, *, resolution=3):
        self.fill_surface_calls = getattr(self, 'fill_surface_calls', [])
        self.fill_surface_calls.append((resolution,))
        return ('fill_surface', len(self.fill_surface_calls))

    def knit_selected(self, *, try_to_form_solid=True, merge_entities=True, **kw):
        self.knit_calls = getattr(self, 'knit_calls', [])
        self.knit_calls.append((try_to_form_solid, merge_entities))
        return ('knit', len(self.knit_calls))

    def sweep_boss(self, *, merge=True):
        self.sweep_boss_calls = getattr(self, 'sweep_boss_calls', [])
        self.sweep_boss_calls.append((merge,))
        return ('sweep_boss', len(self.sweep_boss_calls))

    def sweep_cut(self, *, merge=True):
        self.sweep_cut_calls = getattr(self, 'sweep_cut_calls', [])
        self.sweep_cut_calls.append((merge,))
        return ('sweep_cut', len(self.sweep_cut_calls))


class _MockModelDoc:
    """The minimal ModelDoc surface the translator dispatches to.

    The surface mirrors the real solidworks_com ModelDoc so the
    translator's call sequence matches what a real SW host will see.
    """

    def __init__(self) -> None:
        self.features = _MockFeatures()
        self.plane_calls = []
        self.sketch_calls = 0
        self.bbox = ((-50.0, -30.0, 0.0), (50.0, 30.0, 10.0))
        # Top face used by select_face / find_face_at.
        self.last_face = None
        # Captures the most recent sketch context.
        self._current_sketch = None
        # Records find_face_at calls.
        self.find_face_at_calls = []
        # Records clear_selection and select_object calls.
        self.selection_log = []

    def select_plane(self, label, *, append=False):
        self.plane_calls.append(label)
        return True

    def select_face_by_ray(self, origin, direction):
        self.last_face = ("face-by-ray", origin, direction)
        return self.last_face

    def select_matching_sketch_contours(self, matching=""):
        return 1

    def sketch(self):
        self.sketch_calls += 1
        # Return a context manager that yields a _MockSketch and
        # records the entities added during the with-block.
        outer = self
        sk = _MockSketch()
        return _SketchContext(outer, sk)

    def sketch3d(self):
        self.sketch3d_calls = getattr(self, 'sketch3d_calls', 0) + 1
        outer = self
        sk = _MockSketch()
        return _SketchContext(outer, sk)

    def add_equation(self, name, expression):
        self.equation_calls = getattr(self, 'equation_calls', [])
        self.equation_calls.append((name, expression))

    def delete_equation(self, index):
        self.delete_equation_calls = getattr(self, 'delete_equation_calls', [])
        self.delete_equation_calls.append(index)

    def equations(self):
        return getattr(self, 'equation_calls', [])

    def add_configuration(self, name, *, description='', parent=''):
        self.config_calls = getattr(self, 'config_calls', [])
        self.config_calls.append((name, description, parent))

    def set_active_configuration(self, name):
        self.set_config_calls = getattr(self, 'set_config_calls', [])
        self.set_config_calls.append((name,))

    def suppress_feature_in_config(self, feature_name, config_name):
        self.suppress_calls = getattr(self, 'suppress_calls', [])
        self.suppress_calls.append((feature_name, config_name))

    def unsuppress_feature_in_config(self, feature_name, config_name):
        self.unsuppress_calls = getattr(self, 'unsuppress_calls', [])
        self.unsuppress_calls.append((feature_name, config_name))

    def insert_design_table(self, rows, columns):
        self.design_table_calls = getattr(self, 'design_table_calls', [])
        self.design_table_calls.append((rows, columns))

    def bounding_box(self):
        # Legacy alias for older tests; the real ModelDoc exposes
        # ``part_box`` but we keep this method as a fallback so
        # the translator can resolve either name.
        return self.bbox

    def part_box(self):
        # Returns the SOLIDWORKS 6-tuple form
        # ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
        bb_min, bb_max = self.bbox
        return (bb_min[0], bb_min[1], bb_min[2], bb_max[0], bb_max[1], bb_max[2])

    def bodies(self):
        # v0.2 edge-selection support.  Returns the per-test
        # ``self.body_edges`` list (set by the test) or an empty
        # list when the test does not exercise the v0.2 path.
        return list(getattr(self, "body_edges", []))

    def _make_body(self, edges):
        # Convenience for v0.2 tests: a body whose ``GetEdges``
        # returns the supplied edge list.  The body itself
        # only needs ``GetEdges`` for the translator.
        class _Body:
            def __init__(self, edges):
                self._edges = edges
            def GetEdges(self, flag):
                return self._edges
        return _Body(edges)

    def find_face_at(self, x, y, z, *, require=True):
        self.find_face_at_calls.append((x, y, z))
        # Return a stable face handle so the translator can call
        # ``select_object`` on it.
        return ("face", (x, y, z))

    def clear_selection(self, notify=True):
        self.selection_log.append(("clear",))
        return None

    def select_object(self, obj, *, append=False, mark=0, require=True):
        self.selection_log.append(("select", obj, append, mark))
        return True


class _SketchContext:
    """Implements ``with part.sketch() as sk:`` semantics for the mock."""

    def __init__(self, model: _MockModelDoc, sketch: _MockSketch) -> None:
        self._model = model
        self._sk = sketch

    def __enter__(self):
        self._model._current_sketch = self._sk
        return self._sk

    def __exit__(self, exc_type, exc, tb):
        self._model._current_sketch = None
        return False


class _CapturingSketchContext:
    """Wraps a ``_SketchContext`` and records every method call.

    Used by ``test_polygon_dispatches_to_sketch`` to verify the
    buffered sketch entities get replayed on the SketchBuilder.
    """

    def __init__(self, inner: "_SketchContext", sink: list) -> None:
        self._inner = inner
        self._sink = sink

    def __enter__(self):
        sk = self._inner.__enter__()
        outer = self

        class _Recorder:
            def __getattr__(self, name):
                method = getattr(sk, name)

                def wrapper(*args, **kwargs):
                    # Record both positional and keyword arguments
                    # so callers can assert on the full call shape.
                    outer._sink.append((name, args, kwargs))
                    return method(*args, **kwargs)

                return wrapper
        return _Recorder()

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)


def _compile_sw_via_cad_ai(ir_path: Path) -> dict:
    """Run the cad_ai compiler chain to produce an SW instruction stream.

    The test imports the cad_ai helpers via sys.path injection so
    the chain can run without needing cadpy on the test host.
    """
    from cad_ai import sw_compile  # type: ignore


    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    return sw_compile.compile_sw(ir)


class CadIrToSwContractTests(unittest.TestCase):
    """Verify the translator's call sequence on the mounting_plate example."""

    def test_mounting_plate_extrude_and_cuts(self):
        ir_path = _REPO / "skills" / "cad_ai" / "examples" / "mounting_plate.ir.json"
        stream = _compile_sw_via_cad_ai(ir_path)
        part = _MockModelDoc()
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        CadIrToSw(part).execute(stream)

        # Exactly 1 extrude (the base) and 4 cuts (the 4 corner holes).
        self.assertEqual(len(part.features.extrude_blind_calls), 1,
                          "expected one base extrude")
        self.assertEqual(len(part.features.cut_blind_calls), 4,
                          "expected four hole cuts")

        # Base extrude: depth 10.0, no reverse, merged.
        depth, merge, reverse = part.features.extrude_blind_calls[0]
        self.assertEqual(depth, 0.01)
        self.assertTrue(merge)
        self.assertFalse(reverse)

        # Each cut_blind call uses a positive depth (the
        # through-cut approximation uses bbox-derived depth).
        for depth, _reverse, _normal_cut in part.features.cut_blind_calls:
            self.assertGreater(depth, 0.0,
                                "through-cut depth must be positive")

        # No fillet / chamfer was emitted by mounting_plate.
        self.assertEqual(len(part.features.fillet_calls), 0)

        # The translator opened one sketch per rectangle-and-extrude
        # block, and one per circle-and-cut block.  The mounting
        # plate IR has 5 such blocks.
        self.assertEqual(part.sketch_calls, 5)

        # The plane was selected at least once.
        self.assertGreater(len(part.plane_calls), 0)

    def test_polygon_dispatches_to_sketch(self):
        # Phase-1 contract: sketch_polygon is now a first-class
        # op.  Verify the buffered polygon call reaches the
        # ``SketchBuilder.polygon`` mock with the right args.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        captured: list = []
        original_sketch = part.sketch

        def capturing_sketch():
            ctx = original_sketch()
            return _CapturingSketchContext(ctx, captured)

        part.sketch = capturing_sketch  # type: ignore[assignment]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_polygon",
             "center": [0.0, 0.0], "radius": 12.0, "sides": 6},
            {"op": "sketch_end"},
        ]})
        # We expect one polygon call captured with the buffered
        # arguments: positional (cx, cy, vx, vy) and keyword
        # ``sides=6, inscribed=True``.
        self.assertEqual(len(captured), 1)
        op, args, kwargs = captured[0]
        self.assertEqual(op, "polygon")
        self.assertEqual(args, (0.0, 0.0, 12.0, 0.0))
        self.assertEqual(kwargs, {"sides": 6, "inscribed": True})

    def test_chamfer_dispatches_to_feature(self):
        # Phase-1 contract: chamfer is now a first-class op.  Verify
        # it dispatches a single call to ``features.chamfer_selected``
        # with the size from the IR.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "chamfer", "size": 0.5,
             "selector": {"kind": "all_edges"}},
        ]})
        # One chamfer call captured on the features mock.
        self.assertEqual(len(part.features.chamfer_calls), 1)
        distance, chamfer_type, _options = part.features.chamfer_calls[0]
        self.assertAlmostEqual(distance, 0.5)
        # Default EqualDistance is 16 (swChamferEqualDistance).
        self.assertEqual(chamfer_type, 16)

    def test_chamfer_rejects_non_positive_size(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        with self.assertRaises(NotImplementedError) as ctx:
            translator.execute({"schema": "sw_instructions.v0", "operations": [
                {"op": "chamfer", "size": 0.0,
                 "selector": {"kind": "all_edges"}},
            ]})
        self.assertIn("positive", str(ctx.exception).lower())

    def test_circle_pattern_dispatches_multi_circle(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_circle_pattern",
             "centers": [[0.0, 1.0], [1.0, 0.0]],
             "diameter": 0.5},
            {"op": "sketch_end"},
        ]})
        # The mock's sketch was opened once and the buffer should
        # have produced two circle calls inside it.  We can verify
        # the side effects by looking at the calls log.
        self.assertEqual(part.sketch_calls, 1)

    def test_fillet_supports_top_outer_edges(self):
        # Phase-1 contract: the v0 selector ``top_outer_edges``
        # must dispatch through the same path as ``all_edges``.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "fillet", "radius": 1.0,
             "selector": {"kind": "top_outer_edges"}},
        ]})
        self.assertEqual(len(part.features.fillet_calls), 1)
        radius, _options = part.features.fillet_calls[0]
        self.assertAlmostEqual(radius, 1.0)

    def test_extrude_records_feature_id_in_map(self):
        # v0.2: the IR id carried by feature_id must be
        # registered so a later extrude_cut with target
        # can resolve it.  The mock extrude_blind returns
        # ("feature", N); we use that as the map value.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "feature_id": "base_plate",
             "depth": 5.0, "direction": "+Z"},
        ]})
        self.assertIn("base_plate", translator._feature_by_id)
        self.assertEqual(translator._feature_by_id["base_plate"], ("feature", 1))

    def test_extrude_without_feature_id_does_not_register(self):
        # v0 legacy streams had no feature_id on extrude.
        # The translator must accept them and leave the map empty.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
        ]})
        self.assertEqual(translator._feature_by_id, {})

    def test_extrude_cut_with_target_selects_body(self):
        # v0.2: an extrude_cut carrying a target field must
        # clear the selection and re-select the targeted body
        # before the cut.  The mock records both calls in
        # selection_log; we assert the order.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "feature_id": "base_plate",
             "depth": 5.0, "direction": "+Z"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [2.0, 2.0]},
            {"op": "sketch_end"},
            {"op": "extrude_cut", "target": "base_plate",
             "depth": 1.0},
        ]})
        # One cut must have happened.
        self.assertEqual(len(part.features.cut_blind_calls), 1)
        # The selection log contains a clear + select targeting
        # the body feature returned by extrude_blind.
        clear_calls = [c for c in part.selection_log if c[0] == "clear"]
        select_calls = [c for c in part.selection_log if c[0] == "select"]
        self.assertGreaterEqual(len(clear_calls), 1)
        self.assertGreaterEqual(len(select_calls), 1)
        # The most recent select must target the body feature.
        last_select = select_calls[-1]
        self.assertEqual(last_select[1], ("feature", 1))
        self.assertEqual(last_select[3], 0)  # mark=0 (body)

    def test_extrude_cut_with_unknown_target_falls_back(self):
        # v0.2: an extrude_cut with a target that has not
        # been registered (legacy stream, missing extrude_add)
        # must not crash.  The cut still happens against the
        # active body (the v0 behaviour).
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [2.0, 2.0]},
            {"op": "sketch_end"},
            {"op": "extrude_cut", "target": "ghost_id",
             "depth": 1.0},
        ]})
        self.assertEqual(len(part.features.cut_blind_calls), 1)
        # No select_object on a body feature happened for the
        # unknown target.
        select_for_body = [
            c for c in part.selection_log
            if c[0] == "select" and c[3] == 0
        ]
        self.assertEqual(select_for_body, [])

    def test_fillet_all_edges_via_bodies_get_edges(self):
        # v0.2: when the host exposes ``bodies()`` whose bodies
        # expose ``GetEdges``, the translator must select every
        # edge returned (with append=True, mark=1) and skip the
        # ``v0`` body-feature fallback.  We verify the call sequence
        # in ``selection_log``.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        e1 = ("edge", 1)
        e2 = ("edge", 2)
        e3 = ("edge", 3)
        part.body_edges = [part._make_body([e1, e2, e3])]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "fillet", "radius": 1.0,
             "selector": {"kind": "all_edges"}},
        ]})
        # One clear, then three appends.
        clear_calls = [c for c in part.selection_log if c[0] == "clear"]
        select_calls = [c for c in part.selection_log if c[0] == "select"]
        self.assertEqual(len(clear_calls), 1)
        self.assertEqual(len(select_calls), 3)
        for c in select_calls:
            self.assertTrue(c[2])  # append=True
            self.assertEqual(c[3], 1)  # mark=1 (edge)
        selected_edges = [c[1] for c in select_calls]
        self.assertEqual(selected_edges, [e1, e2, e3])
        # And the fillet call happened.
        self.assertEqual(len(part.features.fillet_calls), 1)

    def test_fillet_top_outer_edges_filters_by_z(self):
        # v0.2: ``top_outer_edges`` must select only the edges
        # whose Z centroid equals the part bbox zmax.  Edges
        # without a centroid are skipped (v0 host compatibility).
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        top_edge = ("edge", "top")
        bot_edge = ("edge", "bot")
        no_centroid = ("edge", "nc")
        body = part._make_body([
            _EdgeWithCentroid(top_edge, (0.0, 0.0, 10.0)),
            _EdgeWithCentroid(bot_edge, (0.0, 0.0, 0.0)),
            no_centroid,  # no .centroid
        ])
        part.body_edges = [body]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "fillet", "radius": 1.0,
             "selector": {"kind": "top_outer_edges"}},
        ]})
        # Only the top edge survives the Z filter.
        select_calls = [c for c in part.selection_log if c[0] == "select"]
        self.assertEqual(len(select_calls), 1)
        self.assertEqual(select_calls[0][1].payload, top_edge)

    def test_fillet_via_bodies_falls_back_when_no_edges_survive(self):
        # v0.2: if the Z filter eliminates every edge, the
        # translator must not silently produce a no-op
        # selection.  The v0 body-feature fallback is used
        # so the SW host gets a real (if imprecise) target.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        bot_edge = _EdgeWithCentroid("edge", (0.0, 0.0, 0.0))
        body = part._make_body([bot_edge])
        part.body_edges = [body]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "fillet", "radius": 1.0,
             "selector": {"kind": "top_outer_edges"}},
        ]})
        # The translator fell back to v0 path.  On the v0 path
        # the mock does not produce a select_object call (the
        # mock's iter_features is a no-op and the v0 fallback
        # ends in select_matching_sketch_contours).  The fillet
        # call still happens so the SW host gets a real feature.
        # The discriminating signal is: NO mark=1 appends on
        # edges (that's the v0.2 path) and exactly one fillet.
        edge_appends = [c for c in part.selection_log
                        if c[0] == "select" and c[3] == 1]
        self.assertEqual(len(edge_appends), 0)
        self.assertEqual(len(part.features.fillet_calls), 1)

    def test_chamfer_uses_v02_edge_dispatch(self):
        # v0.2: chamfer goes through the same per-edge path as
        # fillet.  Two edges -> two appends + one chamfer call.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        e1 = ("edge", 1)
        e2 = ("edge", 2)
        part.body_edges = [part._make_body([e1, e2])]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "select_plane", "plane": "XY"},
            {"op": "sketch_begin"},
            {"op": "sketch_rectangle",
             "center": [0.0, 0.0], "size": [10.0, 10.0]},
            {"op": "sketch_end"},
            {"op": "extrude", "depth": 5.0, "direction": "+Z"},
            {"op": "chamfer", "size": 0.5,
             "selector": {"kind": "all_edges"}},
        ]})
        select_calls = [c for c in part.selection_log if c[0] == "select"]
        self.assertEqual(len(select_calls), 2)
        self.assertEqual(len(part.features.chamfer_calls), 1)

    def test_boolean_union_joins_all_bodies(self):
        # v0.2: boolean_union with all=True must pairwise
        # union every body returned by part.bodies().
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        b1 = ("body", 1)
        b2 = ("body", 2)
        b3 = ("body", 3)
        part.body_edges = [b1, b2, b3]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "boolean_union", "all": True},
        ]})
        # Two unions: b1+b2 -> result, then result+b3
        self.assertEqual(len(part.features.bool_union_calls), 2)
        self.assertEqual(part.features.bool_union_calls[0], (b1, b2))
        self.assertEqual(part.features.bool_union_calls[1],
                         (("union_feature", 1), b3))

    def test_boolean_union_skipped_with_fewer_than_two_bodies(self):
        # v0.2: fewer than two bodies means nothing to union.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        part.body_edges = [("body", 1)]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "boolean_union", "all": True},
        ]})
        self.assertEqual(len(part.features.bool_union_calls), 0)

    def test_boolean_union_skipped_without_all_flag(self):
        # v0.2: all must be True for the union to run.
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        part.body_edges = [("body", 1), ("body", 2)]
        translator = CadIrToSw(part)
        translator.execute({"schema": "sw_instructions.v0", "operations": [
            {"op": "new_part", "name": "x"},
            {"op": "boolean_union", "all": False},
        ]})
        self.assertEqual(len(part.features.bool_union_calls), 0)


    # ---- v0.4 contract tests -------------------------------------------

    def test_revolve_dispatches_to_revolve(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_rectangle', 'center': [0, 0], 'size': [10, 10]},
                {'op': 'sketch_end'},
                {'op': 'revolve', 'feature_id': 'rev1', 'angle': 180, 'axis': '+Z', 'cut': False},
            ],
        })
        self.assertTrue(hasattr(part.features, 'revolve_calls'))
        self.assertEqual(len(part.features.revolve_calls), 1)
        angle, cut, reverse, merge = part.features.revolve_calls[0]
        self.assertEqual(angle, 180.0)
        self.assertEqual(cut, False)
        self.assertEqual(reverse, False)
        self.assertEqual(merge, True)

    def test_loft_boss_dispatches_to_loft(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 10},
                {'op': 'sketch_end'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'loft_boss', 'feature_id': 'loft1', 'closed': False, 'profile_count': 2},
            ],
        })
        self.assertTrue(hasattr(part.features, 'loft_boss_calls'))
        self.assertEqual(len(part.features.loft_boss_calls), 1)
        closed, merge = part.features.loft_boss_calls[0]
        self.assertEqual(closed, False)
        self.assertEqual(merge, True)

    def test_mirror_dispatches_to_mirror(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_rectangle', 'center': [0, 0], 'size': [10, 10]},
                {'op': 'sketch_end'},
                {'op': 'extrude', 'feature_id': 'base', 'depth': 0.01, 'direction': '+Z'},
                {'op': 'mirror', 'features': ['base'], 'plane': 'YZ'},
            ],
        })
        self.assertTrue(hasattr(part.features, 'mirror_calls'))
        self.assertEqual(len(part.features.mirror_calls), 1)
        merge, = part.features.mirror_calls[0]
        self.assertEqual(merge, True)

    def test_linear_pattern_dispatches_to_pattern(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'extrude', 'feature_id': 'hole', 'depth': 0.01, 'direction': '+Z'},
                {'op': 'linear_pattern', 'features': ['hole'], 'direction': 'X', 'spacing': 0.02, 'count': 3},
            ],
        })
        self.assertTrue(hasattr(part.features, 'linear_pattern_calls'))
        self.assertEqual(len(part.features.linear_pattern_calls), 1)
        count, spacing, merge = part.features.linear_pattern_calls[0]
        self.assertEqual(count, 3)
        self.assertEqual(spacing, 0.02)
        self.assertEqual(merge, True)

    def test_circular_pattern_dispatches_to_pattern(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'extrude', 'feature_id': 'hole', 'depth': 0.01, 'direction': '+Z'},
                {'op': 'circular_pattern', 'features': ['hole'], 'axis': 'Z', 'count': 6, 'angle': 360},
            ],
        })
        self.assertTrue(hasattr(part.features, 'circular_pattern_calls'))
        self.assertEqual(len(part.features.circular_pattern_calls), 1)
        count, angle, merge = part.features.circular_pattern_calls[0]
        self.assertEqual(count, 6)
        self.assertEqual(angle, 360.0)
        self.assertEqual(merge, True)

    def test_shell_dispatches_to_shell(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_rectangle', 'center': [0, 0], 'size': [10, 10]},
                {'op': 'sketch_end'},
                {'op': 'extrude', 'feature_id': 'base', 'depth': 0.01, 'direction': '+Z'},
                {'op': 'shell', 'thickness': 0.001, 'faces': []},
            ],
        })
        self.assertTrue(hasattr(part.features, 'shell_calls'))
        self.assertEqual(len(part.features.shell_calls), 1)
        thickness, remove_faces = part.features.shell_calls[0]
        self.assertEqual(thickness, 0.001)
        self.assertEqual(remove_faces, False)

    def test_draft_dispatches_to_draft(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_rectangle', 'center': [0, 0], 'size': [10, 10]},
                {'op': 'sketch_end'},
                {'op': 'extrude', 'feature_id': 'base', 'depth': 0.01, 'direction': '+Z'},
                {'op': 'draft', 'angle': 5.0, 'direction': '+Z', 'faces': []},
            ],
        })
        self.assertTrue(hasattr(part.features, 'draft_calls'))
        self.assertEqual(len(part.features.draft_calls), 1)
        angle, draft_type = part.features.draft_calls[0]
        self.assertEqual(angle, 5.0)
        self.assertEqual(draft_type, 0)


    def test_loft_surface_dispatches_to_loft_surface(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 10},
                {'op': 'sketch_end'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'loft_surface', 'feature_id': 'loft1', 'closed': False, 'profile_count': 2},
            ],
        })
        self.assertTrue(hasattr(part.features, 'loft_surface_calls'))
        self.assertEqual(len(part.features.loft_surface_calls), 1)
        closed, = part.features.loft_surface_calls[0]
        self.assertEqual(closed, False)

    def test_thicken_dispatches_to_thicken(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 10},
                {'op': 'sketch_end'},
                {'op': 'loft_surface', 'feature_id': 'surf1', 'closed': False, 'profile_count': 1},
                {'op': 'thicken', 'surface': 'surf1', 'thickness': 0.002, 'direction': '+Z'},
            ],
        })
        self.assertTrue(hasattr(part.features, 'thicken_calls'))
        self.assertEqual(len(part.features.thicken_calls), 1)
        thickness, direction, merge = part.features.thicken_calls[0]
        self.assertEqual(thickness, 0.002)
        self.assertEqual(merge, True)

    def test_fill_surface_dispatches_to_fill_surface(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'fill_surface', 'boundary': ['edge1', 'edge2']},
            ],
        })
        self.assertTrue(hasattr(part.features, 'fill_surface_calls'))
        self.assertEqual(len(part.features.fill_surface_calls), 1)

    def test_knit_dispatches_to_knit(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 10},
                {'op': 'sketch_end'},
                {'op': 'loft_surface', 'feature_id': 'surf1', 'closed': False, 'profile_count': 1},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'loft_surface', 'feature_id': 'surf2', 'closed': False, 'profile_count': 1},
                {'op': 'knit', 'surfaces': ['surf1', 'surf2']},
            ],
        })
        self.assertTrue(hasattr(part.features, 'knit_calls'))
        self.assertEqual(len(part.features.knit_calls), 1)


    def test_sweep_boss_dispatches_to_sweep(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'select_plane', 'plane': 'XY'},
                {'op': 'sketch_begin'},
                {'op': 'sketch_circle', 'center': [0, 0], 'diameter': 5},
                {'op': 'sketch_end'},
                {'op': 'sketch_3d_path', 'feature_id': 'tube', 'start': [0, 0, 0], 'end': [0.1, 0, 0.05]},
                {'op': 'sweep_boss', 'feature_id': 'tube', 'merge': True},
            ],
        })
        # Verify 3D sketch was created
        self.assertTrue(hasattr(part, 'sketch3d_calls'))
        self.assertEqual(part.sketch3d_calls, 1)
        # Verify sweep was called
        self.assertTrue(hasattr(part.features, 'sweep_boss_calls'))
        self.assertEqual(len(part.features.sweep_boss_calls), 1)
        merge, = part.features.sweep_boss_calls[0]
        self.assertEqual(merge, True)


    def test_equation_dispatches_to_add_equation(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'equation', 'name': 'length', 'expression': '100 + 50'},
            ],
        })
        self.assertTrue(hasattr(part, 'equation_calls'))
        self.assertEqual(len(part.equation_calls), 1)
        self.assertEqual(part.equation_calls[0], ('length', '100 + 50'))


    def test_generate_bom_dispatches_to_bom(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'generate_bom', 'format': 'json', 'output_path': 'bom.json'},
            ],
        })
        # BOM generation is a no-op in mock (ImportError caught)
        # We just verify it does not crash
        self.assertTrue(True)


    def test_add_configuration_dispatches_to_add_configuration(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'add_configuration', 'name': 'ConfigA', 'description': 'Test config', 'parent': ''},
            ],
        })
        self.assertTrue(hasattr(part, 'config_calls'))
        self.assertEqual(len(part.config_calls), 1)
        self.assertEqual(part.config_calls[0], ('ConfigA', 'Test config', ''))

    def test_set_configuration_dispatches_to_set_active(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'set_configuration', 'name': 'ConfigA'},
            ],
        })
        self.assertTrue(hasattr(part, 'set_config_calls'))
        self.assertEqual(len(part.set_config_calls), 1)
        self.assertEqual(part.set_config_calls[0], ('ConfigA',))

    def test_suppress_feature_dispatches_to_suppress(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'suppress_feature', 'feature': 'Cut-Extrude1', 'configuration': 'ConfigA'},
            ],
        })
        self.assertTrue(hasattr(part, 'suppress_calls'))
        self.assertEqual(len(part.suppress_calls), 1)
        self.assertEqual(part.suppress_calls[0], ('Cut-Extrude1', 'ConfigA'))

    def test_design_table_dispatches_to_insert_design_table(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        translator.execute({
            'schema': 'sw_instructions.v0',
            'operations': [
                {'op': 'new_part', 'name': 'test'},
                {'op': 'design_table', 'rows': [['100', '200'], ['150', '250']], 'columns': ['D1', 'D2']},
            ],
        })
        self.assertTrue(hasattr(part, 'design_table_calls'))
        self.assertEqual(len(part.design_table_calls), 1)
        self.assertEqual(part.design_table_calls[0], ([['100', '200'], ['150', '250']], ['D1', 'D2']))

    def test_unsupported_plane_raises(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        with self.assertRaises(NotImplementedError):
            translator._dispatch({"op": "select_plane", "plane": "ZZ"})

    def test_invalid_schema_rejected(self):
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw

        part = _MockModelDoc()
        translator = CadIrToSw(part)
        with self.assertRaises(ValueError) as ctx:
            translator.execute({"schema": "wrong", "operations": []})
        self.assertIn("unsupported SW instruction schema", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
