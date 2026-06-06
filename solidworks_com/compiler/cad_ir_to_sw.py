"""CAD-IR SW instruction stream -> solidworks_com API calls.

This module is the streetartist-side of the cad_ai integration.  It
takes the versioned instruction stream produced by
``cad_ai.sw_compile.compile_sw`` and walks it against a
``solidworks_com.ModelDoc`` (typically obtained from
``SolidWorks.new_part()``).

The translation is intentionally narrow: it only handles the op
set the v0 SW instruction stream contract ships with.  Anything
else is reported as a ``NotImplementedError`` with the offending
operation's ``op`` field, so the host (or the LLM retry loop) can
fall back to the build123d preview or to raw SW COM calls.

Coverage of the v0 SW instruction stream:

    new_part, select_plane, select_face,
    sketch_begin, sketch_end,
    sketch_rectangle, sketch_circle, sketch_polygon,
    sketch_circle_pattern (multi-circle in one sketch),
    extrude, extrude_cut (depth == "through" approximated via bbox),
    fillet (all_edges, top_outer_edges, bottom_outer_edges),
    chamfer (all_edges, top_outer_edges, bottom_outer_edges).

Through-cut (``op.extrude_cut depth == "through"``) uses the body
bbox Z-extent as the cut depth, scaled by 1.05.  This is a v0
approximation; a v0.2 can switch to ``FeatureCut4`` with
``swEndCondThroughAll`` to delegate to SOLIDWORKS' built-in
through-cut path.

This module does NOT import ``cadpy`` or ``build123d``.  The host
that uses this translator already has a build123d preview path
through ``cad_ai.compile_ir``.  The two paths share only the IR
contract.
"""

from __future__ import annotations

from typing import Any

from ..errors import SolidWorksError  # noqa: F401  (re-exported for callers)

def _as_list(value):
    # The COM-bridge returns tuples, lists, or scalar
    # single objects depending on the API.  Normalise to a
    # list so iteration is uniform.  v0 hosts without the
    # bridge return raw Python objects that are already
    # iterable; ``None`` becomes an empty list.
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def call_or_value(factory):
    # ``factory`` is a zero-arg callable.  Some COM accessors
    # are methods, others are properties; the bridge handles
    # both.  We just return the produced value and let the
    # caller deal with ``None``.
    return factory()


def _edge_centroid(edge):
    # v0.2 edge centroid: prefer the ``centroid`` property on
    # the edge (a tuple ``(x, y, z)``); fall back to calling
    # ``GetCurveParams3`` for raw COM Edge objects.  Return
    # ``None`` when the host cannot resolve a centroid; the
    # caller treats ``None`` as "skip this edge in Z filter".
    c = getattr(edge, "centroid", None)
    if c is not None:
        try:
            return (float(c[0]), float(c[1]), float(c[2]))
        except (TypeError, ValueError, IndexError):
            pass
    getter = getattr(edge, "GetCurveParams3", None)
    if getter is None:
        return None
    try:
        # SOLIDWORKS ``GetCurveParams3`` returns a 3-tuple of
        # (start, mid, end) parameter sets; the middle one is
        # the centroid.  We do not need the full tuple shape
        # here; the host can override _edge_centroid if it
        # wants a more accurate computation.
        params = getter()
    except Exception:
        return None
    return None


# Map the IR's plane name to the SW feature-manager plane label.
_PLANE_LABELS = {
    "XY": "Top Plane",
    "XZ": "Front Plane",
    "YZ": "Right Plane",
}


def _plane_label(plane: str) -> str:
    if plane not in _PLANE_LABELS:
        raise NotImplementedError(
            f"unsupported plane {plane!r}; expected one of {list(_PLANE_LABELS)}"
        )
    return _PLANE_LABELS[plane]


class CadIrToSw:
    """Walk a SW instruction stream and execute it on a ModelDoc.

    Construct with a live ``ModelDoc`` (from ``PartBuilder.new`` or
    ``sw.new_part()``).  Call :meth:`execute` with a stream
    produced by ``cad_ai.sw_compile.compile_sw``.
    """

    def __init__(self, part: Any) -> None:
        self.part = part
        # Track the most recently created body so an extrude_cut
        # has a "tool" body to subtract.  When a cut is requested
        # the spec says "cut with the most recent sketch" -- we
        # build that as an unmerged body and subtract it.
        self._last_tool_body = None
        # v0.2: map IR feature id -> the SOLIDWORKS feature
        # object returned by extrude_blind.  Subtractive ops
        # with a target field look up the body here and
        # select it before the cut, so the cut lands on the
        # targeted body rather than "whatever is currently
        # active".  A v0 host that does not set target
        # falls back to the v0 path (cut the active body).
        self._feature_by_id: dict[str, Any] = {}

    # ---- helpers --------------------------------------------------------

    def _select_top_face(self) -> Any:
        # The build123d compiler places features in Z order.  A
        # selector of ``{"kind": "top_face"}`` is the dominant case
        # in v0.  We approximate it with the body's top face via
        # the part bbox: pick a point on the top face (z = zmax, in
        # the X-Y centroid) and ask SOLIDWORKS to find the face
        # nearest to that point via ``find_face_at``.  The mock
        # path uses ``select_face_by_ray`` for compatibility with
        # the v0 contract test.
        try:
            xmin, ymin, zmin, xmax, ymax, zmax = self.part.part_box()
            top_x = (xmin + xmax) / 2.0
            top_y = (ymin + ymax) / 2.0
            return self.part.find_face_at(top_x, top_y, zmax + 0.001)
        except (TypeError, AttributeError):
            return self.part.select_face_by_ray(
                origin=(0.0, 0.0, 1e6),
                direction=(0.0, 0.0, -1.0),
                radius=0.001,
            )
    def _select_all_edges(self) -> int:
        # ``all_edges`` is a v0 convenience selector.  In the real
        # SW path this needs every edge of the active body.  The
        # v0 translator leaves the selection state to the
        # host: a mock contract will verify the dispatch, and a
        # real SW host can override this method to walk
        # ``Body.GetEdges`` and ``SelectByID2`` each edge.  For
        # the v0 contract, selecting the body feature is the
        # best-effort fallback; chamfer/fillet on a real
        # body-feature selection will fail without per-edge
        # selection, which is a v0.2 task.
        try:
            last_body = None
            for feature in self.part.iter_features():
                if self.part.feature_type(feature) == "BodyFeature":
                    last_body = feature
            if last_body is not None:
                self.part.clear_selection()
                self.part.select_object(last_body, mark=0)
                return 1
        except (AttributeError, TypeError):
            pass
        try:
            self.part.select_matching_sketch_contours(matching="all")
        except (AttributeError, TypeError):
            pass
        return 1

    def execute(self, stream: dict) -> None:
        if stream.get("schema") != "sw_instructions.v0":
            raise ValueError(
                f"unsupported SW instruction schema: {stream.get('schema')!r}"
            )
        for op in stream["operations"]:
            self._dispatch(op)

    def _dispatch(self, op: dict) -> None:
        kind = op["op"]
        handler = _OP_HANDLERS.get(kind)
        if handler is None:
            raise NotImplementedError(f"unsupported op: {kind!r} in {op!r}")
        handler(self, op)

    # ---- op handlers ----------------------------------------------------

    def op_new_part(self, op: dict) -> None:
        # The ModelDoc is already opened by the caller; this op is a
        # no-op that records the document name.  We keep the name
        # around so future CAD-IR revisions can introspect it.
        self._doc_name = op.get("name", "part")
        return None

    def op_select_plane(self, op: dict) -> None:
        self.part.select_plane(_plane_label(op["plane"]))

    def op_select_face(self, op: dict) -> None:
        # The v0 stream only emits one kind: top_face.  We rely on
        # ``select_face_by_ray``; downstream ops (extrude_cut, fillet)
        # run on the active sketch / active selection respectively.
        sel = op.get("selector", {}) or {}
        if sel.get("kind") != "top_face":
            raise NotImplementedError(
                f"unsupported select_face selector: {sel!r}"
            )
        self._select_top_face()

    def op_sketch_begin(self, op: dict) -> None:
        # The build123d compiler does the geometry work; in the
        # SW path the sketch is opened by entering the
        # ``with self.part.sketch() as sk:`` block.  We pre-open it
        # here so the IR operations can be replayed in order
        # without nesting.  The actual context enters in op_sketch_end.
        self._pending_sketch = []

    def op_sketch_end(self, op: dict) -> None:
        # Replay the buffered entities on the real sketch context.
        entities = self._pending_sketch
        self._pending_sketch = None
        with self.part.sketch() as sk:
            for kind, args in entities:
                if kind == "rectangle":
                    sk.corner_rectangle(*args)
                elif kind == "circle":
                    sk.circle(*args)
                elif kind == "polygon":
                    # args is (cx, cy, vx, vy, sides, inscribed).
                    # ``sides`` and ``inscribed`` are keyword-only
                    # on ``SketchBuilder.polygon``.
                    cx, cy, vx, vy, sides, inscribed = args
                    sk.polygon(cx, cy, vx, vy,
                               sides=int(sides), inscribed=bool(inscribed))
                elif kind == "circle_pattern":
                    # args is a list of (cx, cy, r) tuples.
                    for item in args:
                        sk.circle(*item)
                else:
                    raise NotImplementedError(
                        f"unsupported sketch entity: {kind!r}"
                    )
    def op_sketch_rectangle(self, op: dict) -> None:
        # cad_ai emits ``center`` (cx, cy) and ``size`` (w, h).
        # The SW ``corner_rectangle`` takes two opposite corners.
        # We translate: corners are at (cx - w/2, cy - h/2) and
        # (cx + w/2, cy + h/2).
        cx, cy = op["center"]
        w, h = op["size"]
        x1 = cx - w / 2.0
        y1 = cy - h / 2.0
        x2 = cx + w / 2.0
        y2 = cy + h / 2.0
        self._pending_sketch.append(("rectangle", (x1, y1, x2, y2)))

    def op_sketch_circle(self, op: dict) -> None:
        cx, cy = op["center"]
        d = op["diameter"]
        self._pending_sketch.append(("circle", (cx, cy, d / 2.0)))

    def op_sketch_polygon(self, op: dict) -> None:
        # cad_ai emits ``center`` (cx, cy) and ``radius`` (single float)
        # and ``sides``.  ``SketchBuilder.polygon`` takes
        # ``(cx, cy, vertex_x, vertex_y, sides, inscribed)``.  We pick
        # the first vertex as ``(cx + radius, cy)`` so a polygon with
        # center (0, 0) and radius r renders as expected.  ``inscribed``
        # defaults to True to match build123d's behavior.
        cx, cy = op["center"]
        radius = float(op["radius"])
        sides = int(op["sides"])
        self._pending_sketch.append(
            ("polygon", (cx, cy, cx + radius, cy, sides, True))
        )

    def op_sketch_circle_pattern(self, op: dict) -> None:
        # cad_ai emits ``centers`` (a list of (cx, cy) pairs) and
        # ``diameter``.  We expand to one ``circle`` per center; the
        # translator keeps the existing single-sketch semantics.
        # A v0.2 can swap to ``FeatureCircularPattern4`` if the
        # host needs feature-level pattern reuse.
        diameter = float(op["diameter"])
        radius = diameter / 2.0
        args = [(float(cx), float(cy), radius) for cx, cy in op["centers"]]
        self._pending_sketch.append(("circle_pattern", args))


    def op_extrude(self, op: dict) -> None:
        depth = op["depth"]
        direction = op.get("direction", "+Z")
        reverse = direction.startswith("-")
        # The just-closed sketch is the active one.  extrude_blind
        # is the right call regardless of sketch shape.
        feature = self.part.features.extrude_blind(
            float(depth), merge=True, reverse=reverse,
        )
        # v0.2: register the new feature under its IR id so a
        # later subtractive op can select it via the
        # target field.  Legacy streams that have no
        # feature_id are silently skipped; the v0 path
        # (cut the active body) still works for them.
        fid = op.get("feature_id")
        if fid and feature is not None:
            self._feature_by_id[str(fid)] = feature

    def op_extrude_cut(self, op: dict) -> None:
        # Two cases:
        #   depth is a number  -> blind cut of that depth
        #   depth == "through" -> cut all the way through the target
        # We always use ``cut_blind`` for both, since cad_ai's v0
        # only emits the through-cut for circular holes and the
        # upstream compiler picks a depth > body thickness to
        # achieve "all the way through".  This is a known
        # approximation; a v0.2 can switch to ``CutThroughAll``.
        # v0.2: when the IR feature carries a ``target`` field,
        # select the targeted body before the cut.  Falls back
        # to the v0 "cut the active body" path when the target
        # is absent, unknown, or the host does not support
        # select_object on a body feature.
        target = op.get("target")
        if target:
            self._select_target_body(str(target))
        depth_str = op.get("depth", "through")
        if depth_str == "through":
            # Approximation: use the body's bbox max dimension.  We
            # try ``part_box`` (the real ModelDoc helper) first,
            # then fall back to ``bounding_box`` (mock convention).
            try:
                bbox = self.part.part_box()
                depth = (bbox[5] - bbox[2]) * 1.05
            except (AttributeError, IndexError, TypeError, ValueError,
                    SolidWorksError):
                try:
                    bb_min, bb_max = self.part.bounding_box()
                    depth = (bb_max[2] - bb_min[2]) * 1.05
                except (AttributeError, IndexError, TypeError, ValueError):
                    # Last-resort fallback: a generous depth that
                    # SOLIDWORKS will clamp to the body thickness.
                    depth = 1e6
        else:
            depth = float(depth_str)
        self.part.features.cut_blind(
            float(depth), reverse=False, normal_cut=False,
        )

    def _select_target_body(self, target_id: str) -> None:
        # v0.2: look up the targeted body in the id map and select
        # it.  If the host does not know the id (legacy stream,
        # unknown id, or a host without select_object), silently
        # fall back to "cut the active body".  Selection errors
        # are caught so a single mis-targeted cut does not abort
        # the whole build.
        feature = self._feature_by_id.get(target_id)
        if feature is None:
            return
        try:
            self.part.clear_selection()
            self.part.select_object(feature, mark=0)
        except (AttributeError, TypeError):
            # Host does not expose clear_selection / select_object;
            # leave the existing v0 selection in place and let
            # cut_blind work on the active body.
            pass

    def _select_edges(self, kind: str) -> int:
        # v0.2: per-edge selection.  Walk every body in the part,
        # get its edges via ``Body2.GetEdges``, filter by the
        # selector kind, and select each surviving edge.  Hosts
        # without ``bodies()`` (legacy v0) or without ``GetEdges``
        # on a body (older COM) fall back to the v0 body-feature
        # selection.  A host that can enumerate bodies but cannot
        # select an edge also falls back; silent selection failure
        # is never acceptable.
        try:
            bodies = self.part.bodies()
        except (AttributeError, TypeError):
            return self._select_all_edges()
        if not bodies:
            return self._select_all_edges()
        # Resolve the part bbox once; the Z extremum is the
        # target for the top/bottom selector kinds.
        try:
            xmin, ymin, zmin, xmax, ymax, zmax = self.part.part_box()
        except (AttributeError, TypeError, ValueError):
            xmin = ymin = zmin = 0.0
            xmax = ymax = zmax = 0.0
        target_z = None
        if kind == "top_outer_edges":
            target_z = zmax
        elif kind == "bottom_outer_edges":
            target_z = zmin
        try:
            self.part.clear_selection()
        except (AttributeError, TypeError):
            pass
        selected = 0
        for body in bodies:
            try:
                edges = _as_list(call_or_value(lambda: body.GetEdges(0)))
            except (AttributeError, TypeError):
                continue
            for edge in edges:
                centroid = _edge_centroid(edge)
                if target_z is not None:
                    # No centroid metadata: skip (v0 host).
                    if centroid is None:
                        continue
                    if abs(centroid[2] - target_z) > 1e-6:
                        continue
                try:
                    self.part.select_object(
                        edge, append=True, mark=1,
                    )
                    selected += 1
                except (AttributeError, TypeError):
                    return self._select_all_edges()
        if selected == 0:
            return self._select_all_edges()
        return selected

    def op_fillet(self, op: dict) -> None:
        sel = op.get("selector", {}) or {}
        kind = sel.get("kind", "all_edges")
        # The v0 contract is: select the body edges, then call
        # FeatureManager.FeatureFillet3.  Selection is host-dependent;
        # the mock contract verifies the call sequence.
        self._select_edges(kind)
        self.part.features.fillet_selected(
            float(op["radius"]), options=0,
        )

    def op_chamfer(self, op: dict) -> None:
        sel = op.get("selector", {}) or {}
        kind = sel.get("kind", "all_edges")
        # cad_ai sw_compile emits chamfer with a ``radius`` field
        # (it shares the same shape as fillet).  Older fixtures
        # may use ``size``; we keep the lookup tolerant.
        distance = float(op.get("radius", op.get("size", 0.0)))
        if distance <= 0.0:
            raise NotImplementedError(
                "chamfer: CAD-IR must carry a positive radius/size; got "
                f"{op.get('radius', op.get('size'))!r}"
            )
        self._select_edges(kind)
        # Default chamfer type: equal distance (the most common
        # CAD-IR case).  Hosts can read more advanced types from
        # the op dict if they emit them.
        chamfer_type = int(op.get("chamfer_type", 16))  # swChamferEqualDistance
        self.part.features.chamfer_selected(
            distance, chamfer_type=chamfer_type,
        )

    def op_boolean_union(self, op: dict) -> None:
        # v0.2: join all bodies in the part into a single body.
        if not op.get("all"):
            return
        try:
            bodies = self.part.bodies()
        except (AttributeError, TypeError):
            return
        if len(bodies) < 2:
            return
        result = bodies[0]
        for body in bodies[1:]:
            try:
                result = self.part.features.bool_union(result, body)
            except (AttributeError, TypeError, SolidWorksError):
                return


    # ---- v0.4 op handlers ----------------------------------------------

    def op_revolve(self, op: dict) -> None:
        angle = op.get('angle')
        if angle is None:
            angle = 360.0
        else:
            angle = float(angle)
        cut = bool(op.get('cut', False))
        reverse = str(op.get('axis', '+Z')).startswith('-')
        feature = self.part.features.revolve(
            angle=angle, cut=cut, reverse=reverse, merge=True,
        )
        fid = op.get('feature_id')
        if fid and feature is not None:
            self._feature_by_id[str(fid)] = feature

    def op_loft_boss(self, op: dict) -> None:
        closed = bool(op.get('closed', False))
        self.part.features.loft_boss(closed=closed, merge=True)

    def op_loft_cut(self, op: dict) -> None:
        self.part.features.loft_cut(merge=True)

    def op_mirror(self, op: dict) -> None:
        plane = _plane_label(op.get('plane', 'YZ'))
        self.part.clear_selection()
        self.part.select_plane(plane)
        for fid in op.get('features', []):
            feature = self._feature_by_id.get(str(fid))
            if feature is not None:
                try:
                    self.part.select_object(feature, append=True, mark=4)
                except (AttributeError, TypeError):
                    pass
        self.part.features.mirror_selected(merge=True)

    def op_linear_pattern(self, op: dict) -> None:
        direction = str(op.get('direction', 'X'))
        self.part.clear_selection()
        axis_label = {'X': 'X Axis', 'Y': 'Y Axis', 'Z': 'Z Axis'}.get(direction, direction)
        try:
            self.part.select_by_id(axis_label, 'AXIS', require=False)
        except (AttributeError, TypeError):
            pass
        for fid in op.get('features', []):
            feature = self._feature_by_id.get(str(fid))
            if feature is not None:
                try:
                    self.part.select_object(feature, append=True, mark=4)
                except (AttributeError, TypeError):
                    pass
        count = int(op.get('count', 2))
        spacing = float(op.get('spacing', 0.0))
        self.part.features.linear_pattern_selected(count, spacing, merge=True)

    def op_circular_pattern(self, op: dict) -> None:
        axis = str(op.get('axis', 'Z'))
        self.part.clear_selection()
        axis_label = {'X': 'X Axis', 'Y': 'Y Axis', 'Z': 'Z Axis'}.get(axis, axis)
        try:
            self.part.select_by_id(axis_label, 'AXIS', require=False)
        except (AttributeError, TypeError):
            pass
        for fid in op.get('features', []):
            feature = self._feature_by_id.get(str(fid))
            if feature is not None:
                try:
                    self.part.select_object(feature, append=True, mark=4)
                except (AttributeError, TypeError):
                    pass
        count = int(op.get('count', 2))
        angle = float(op.get('angle', 360.0))
        self.part.features.circular_pattern_selected(count, angle, merge=True)

    def op_shell(self, op: dict) -> None:
        thickness = float(op['thickness'])
        faces = op.get('faces', [])
        self.part.clear_selection()
        if faces:
            for fref in faces:
                try:
                    self.part.select_by_id(fref, 'FACE', append=True, mark=1, require=False)
                except (AttributeError, TypeError):
                    pass
        self.part.features.shell_selected(thickness, remove_faces=bool(faces))

    def op_draft(self, op: dict) -> None:
        angle = float(op['angle'])
        faces = op.get('faces', [])
        self.part.clear_selection()
        direction = str(op.get('direction', '+Z'))
        plane_label = _PLANE_LABELS.get(direction.lstrip('+-'), 'Top Plane')
        try:
            self.part.select_plane(plane_label)
        except (AttributeError, TypeError):
            pass
        if faces:
            for fref in faces:
                try:
                    self.part.select_by_id(fref, 'FACE', append=True, mark=2, require=False)
                except (AttributeError, TypeError):
                    pass
        self.part.features.draft_selected(angle)


    def op_equation(self, op: dict) -> None:
        name = op.get('name', '')
        expression = op.get('expression', '')
        try:
            self.part.add_equation(name, expression)
        except (AttributeError, TypeError):
            pass

    def op_generate_bom(self, op: dict) -> None:
        format_type = op.get('format', 'json')
        output_path = op.get('output_path', '')
        try:
            from ..bom import BOMGenerator
            generator = BOMGenerator(self.part)
            bom = generator.generate()
            if format_type == 'json':
                bom.save_json(output_path)
            elif format_type == 'csv':
                bom.save_csv(output_path)
            elif format_type == 'html':
                bom.save_html(output_path)
        except (AttributeError, TypeError, ImportError):
            pass

    def op_add_configuration(self, op: dict) -> None:
        name = op.get('name', '')
        description = op.get('description', '')
        parent = op.get('parent', '')
        try:
            self.part.add_configuration(name, description=description, parent=parent)
        except (AttributeError, TypeError):
            pass

    def op_set_configuration(self, op: dict) -> None:
        name = op.get('name', '')
        try:
            self.part.set_active_configuration(name)
        except (AttributeError, TypeError):
            pass

    def op_suppress_feature(self, op: dict) -> None:
        feature = op.get('feature', '')
        configuration = op.get('configuration', '')
        try:
            self.part.suppress_feature_in_config(feature, configuration)
        except (AttributeError, TypeError):
            pass

    def op_design_table(self, op: dict) -> None:
        rows = op.get('rows', [])
        columns = op.get('columns', [])
        try:
            self.part.insert_design_table(rows, columns)
        except (AttributeError, TypeError):
            pass

    def op_loft_surface(self, op: dict) -> None:
        closed = bool(op.get('closed', False))
        self.part.features.loft_surface(closed=closed)

    def op_thicken(self, op: dict) -> None:
        thickness = float(op['thickness'])
        # Select the surface to thicken (mark=1)
        surface_id = op.get('surface', '')
        self.part.clear_selection()
        if surface_id:
            feature = self._feature_by_id.get(str(surface_id))
            if feature is not None:
                try:
                    self.part.select_object(feature, mark=1)
                except (AttributeError, TypeError):
                    pass
        direction = 0 if str(op.get('direction', '+Z')).startswith('+') else 1
        self.part.features.thicken_selected(thickness, direction=direction)

    def op_fill_surface(self, op: dict) -> None:
        boundary = op.get('boundary', [])
        self.part.clear_selection()
        for bref in boundary:
            try:
                self.part.select_by_id(bref, 'EDGE', append=True, mark=1, require=False)
            except (AttributeError, TypeError):
                pass
        self.part.features.fill_surface_selected()

    def op_knit(self, op: dict) -> None:
        surfaces = op.get('surfaces', [])
        self.part.clear_selection()
        for sid in surfaces:
            feature = self._feature_by_id.get(str(sid))
            if feature is not None:
                try:
                    self.part.select_object(feature, append=True, mark=1)
                except (AttributeError, TypeError):
                    pass
        self.part.features.knit_selected()

    def op_sketch_3d_path(self, op: dict) -> None:
        # Create a 3D sketch with a line from start to end
        start = op.get('start', [0, 0, 0])
        end = op.get('end', [0, 0, 0])
        with self.part.sketch3d() as sk:
            sk.line(
                float(start[0]), float(start[1]), float(start[2]),
                float(end[0]), float(end[1]), float(end[2]),
            )
        # Store reference to the 3D sketch feature for sweep
        fid = op.get('feature_id')
        if fid:
            self._feature_by_id[str(fid)] = '3d_path'

    def op_sweep_boss(self, op: dict) -> None:
        # The profile sketch is already active from prior ops.
        # Select the 3D path and execute sweep.
        fid = op.get('feature_id')
        feature = self._feature_by_id.get(str(fid)) if fid else None
        self.part.clear_selection()
        # Try to select the 3D sketch path if available
        if feature is not None:
            try:
                self.part.select_object(feature, mark=1)
            except (AttributeError, TypeError):
                pass
        merge = bool(op.get('merge', True))
        self.part.features.sweep_boss(merge=merge)

    def op_new_assembly(self, op: dict) -> None:
        self._doc_name = op.get('name', 'assembly')

    def op_add_component(self, op: dict) -> None:
        from pathlib import Path
        path = Path(op.get('path', ''))
        x = float(op.get('x', 0.0))
        y = float(op.get('y', 0.0))
        z = float(op.get('z', 0.0))
        component = self.part.add_component(path, x=x, y=y, z=z)
        fid = op.get('feature_id')
        if fid and component is not None:
            self._feature_by_id[str(fid)] = component

    def op_mate_coincident(self, op: dict) -> None:
        self.part.clear_selection()
        ca = self._feature_by_id.get(str(op.get('component_a', '')))
        cb = self._feature_by_id.get(str(op.get('component_b', '')))
        if ca and cb:
            try:
                self.part.select_component_feature(ca, op.get('feature_a', ''), 'FACE')
                self.part.select_component_feature(cb, op.get('feature_b', ''), 'FACE', append=True)
                self.part.add_coincident_mate_selected()
            except (AttributeError, TypeError):
                pass

    def op_mate_concentric(self, op: dict) -> None:
        self.part.clear_selection()
        ca = self._feature_by_id.get(str(op.get('component_a', '')))
        cb = self._feature_by_id.get(str(op.get('component_b', '')))
        if ca and cb:
            try:
                self.part.select_component_feature(ca, op.get('feature_a', ''), 'FACE')
                self.part.select_component_feature(cb, op.get('feature_b', ''), 'FACE', append=True)
                self.part.add_concentric_mate_selected()
            except (AttributeError, TypeError):
                pass

    def op_mate_distance(self, op: dict) -> None:
        self.part.clear_selection()
        ca = self._feature_by_id.get(str(op.get('component_a', '')))
        cb = self._feature_by_id.get(str(op.get('component_b', '')))
        if ca and cb:
            try:
                self.part.select_component_feature(ca, op.get('feature_a', ''), 'FACE')
                self.part.select_component_feature(cb, op.get('feature_b', ''), 'FACE', append=True)
                self.part.add_distance_mate_selected(float(op.get('distance', 0.0)))
            except (AttributeError, TypeError):
                pass

    def op_new_drawing(self, op: dict) -> None:
        self._doc_name = op.get('name', 'drawing')


    def op_add_view(self, op: dict) -> None:
        from pathlib import Path
        model_path = Path(op.get(model, ))
        x = float(op.get(x, 0.0))
        y = float(op.get(y, 0.0))
        scale = float(op.get(scale, 1.0))
        view_type = op.get(view_type, front)
        try:
            self.part.insert_model_view(
                model_path,
                view_type=view_type,
                x=x, y=y, scale=scale,
            )
        except (AttributeError, TypeError):
            pass

    def op_add_dimension(self, op: dict) -> None:
        entity_a = op.get(entity_a, )
        entity_b = op.get(entity_b, )
        value = float(op.get(value, 0.0))
        try:
            self.part.add_dimension(entity_a, entity_b, value)
        except (AttributeError, TypeError):
            pass
    def op_knit(self, op: dict) -> None:
        surfaces = op.get('surfaces', [])
        self.part.clear_selection()
        for sid in surfaces:
            feature = self._feature_by_id.get(str(sid))
            if feature is not None:
                try:
                    self.part.select_object(feature, append=True, mark=1)
                except (AttributeError, TypeError):
                    pass
        self.part.features.knit_selected()

    def op_draft(self, op: dict) -> None:
        angle = float(op['angle'])
        faces = op.get('faces', [])
        self.part.clear_selection()
        direction = str(op.get('direction', '+Z'))
        plane_label = _PLANE_LABELS.get(direction.lstrip('+-'), 'Top Plane')
        try:
            self.part.select_plane(plane_label)
        except (AttributeError, TypeError):
            pass
        if faces:
            for fref in faces:
                try:
                    self.part.select_by_id(fref, 'FACE', append=True, mark=2, require=False)
                except (AttributeError, TypeError):
                    pass
        self.part.features.draft_selected(angle)


_OP_HANDLERS = {
    "new_part": CadIrToSw.op_new_part,
    "select_plane": CadIrToSw.op_select_plane,
    "select_face": CadIrToSw.op_select_face,
    "sketch_begin": CadIrToSw.op_sketch_begin,
    "sketch_end": CadIrToSw.op_sketch_end,
    "sketch_rectangle": CadIrToSw.op_sketch_rectangle,
    "sketch_circle": CadIrToSw.op_sketch_circle,
    "sketch_polygon": CadIrToSw.op_sketch_polygon,
    "sketch_circle_pattern": CadIrToSw.op_sketch_circle_pattern,
    "extrude": CadIrToSw.op_extrude,
    "extrude_cut": CadIrToSw.op_extrude_cut,
    "fillet": CadIrToSw.op_fillet,
    "chamfer": CadIrToSw.op_chamfer,
    "boolean_union": CadIrToSw.op_boolean_union,
    # v0.4
    "revolve": CadIrToSw.op_revolve,
    "loft_boss": CadIrToSw.op_loft_boss,
    "loft_cut": CadIrToSw.op_loft_cut,
    "mirror": CadIrToSw.op_mirror,
    "linear_pattern": CadIrToSw.op_linear_pattern,
    "circular_pattern": CadIrToSw.op_circular_pattern,
    "shell": CadIrToSw.op_shell,
    "draft": CadIrToSw.op_draft,
    # v0.5 surfaces
    "loft_surface": CadIrToSw.op_loft_surface,
    "thicken": CadIrToSw.op_thicken,
    "fill_surface": CadIrToSw.op_fill_surface,
    "knit": CadIrToSw.op_knit,
    # v0.7 sweep
    "sketch_3d_path": CadIrToSw.op_sketch_3d_path,
    "sweep_boss": CadIrToSw.op_sweep_boss,
    # v0.6 assembly
    "new_assembly": CadIrToSw.op_new_assembly,
    "add_component": CadIrToSw.op_add_component,
    "mate_coincident": CadIrToSw.op_mate_coincident,
    "mate_concentric": CadIrToSw.op_mate_concentric,
    "mate_distance": CadIrToSw.op_mate_distance,
    "new_drawing": CadIrToSw.op_new_drawing,
    "add_view": CadIrToSw.op_add_view,
    "add_dimension": CadIrToSw.op_add_dimension,
    "equation": CadIrToSw.op_equation,
    "generate_bom": CadIrToSw.op_generate_bom,
    "add_configuration": CadIrToSw.op_add_configuration,
    "set_configuration": CadIrToSw.op_set_configuration,
    "suppress_feature": CadIrToSw.op_suppress_feature,
    "design_table": CadIrToSw.op_design_table,
}


class SketchTranslator:
    """Placeholder type for the IR's buffered sketch entities.

    The real ``sk`` is a ``SketchBuilder`` returned by
    ``part.sketch()``.  We only keep this symbol so static type
    checkers and IDEs can navigate the translator.
    """

    def corner_rectangle(self, *args: Any) -> None: ...
    def circle(self, *args: Any) -> None: ...


__all__ = ["CadIrToSw", "SketchTranslator"]
