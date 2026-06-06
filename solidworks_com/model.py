from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .com import (
    call_member,
    call_or_value,
    double_array,
    empty_dispatch,
    empty_variant,
    import_pywin32,
    int_byref,
    member_value,
    unpack_out_call,
    variant_array,
    variant_byref,
)
from .constants import (
    ChamferOption,
    ChamferType,
    ConstraintType,
    EndCondition,
    MoveRollbackBarTo,
    RefPlaneConstraint,
    SaveAsOptions,
    SaveAsVersion,
    SelectType,
)
from .errors import SolidWorksError
from .geometry import Point, flatten_points
from .units import deg

logger = logging.getLogger(__name__)

FeaturePredicate = Callable[[Any], bool]
SegmentPredicate = Callable[["SketchSegment"], bool]
ContourPredicate = Callable[["SketchContour"], bool]


@dataclass(frozen=True)
class SketchSegment:
    model: ModelDoc
    com: Any

    @property
    def type(self) -> int | None:
        try:
            return int(member_value(self.com, "GetType"))
        except Exception:
            return None

    @property
    def curve(self) -> Any | None:
        return member_value(self.com, "GetCurve", None)

    def select(self, *, append: bool = False, mark: int = 0, require: bool = True) -> bool:
        return self.model.select_object(self.com, append=append, mark=mark, require=require)

    def delete(self) -> None:
        self.model.clear_selection()
        self.select()
        self.model.delete_selected()

    def curve_params(self) -> list[float]:
        curve = self.curve
        if curve is None:
            return []
        for name in ("CircleParams", "LineParams", "EllipseParams"):
            try:
                value = member_value(curve, name, None)
            except Exception:
                value = None
            if value is not None:
                return [float(item) for item in list(value)]
        return []


class ModelDoc:
    def __init__(self, com: Any, app: Any | None = None) -> None:
        self.com = com
        self.app = app

    @property
    def title(self) -> str:
        return str(member_value(self.com, "GetTitle"))

    @property
    def extension(self) -> Any:
        return self.com.Extension

    @property
    def features(self) -> FeatureTools:
        return FeatureTools(self)

    @property
    def sketch_manager(self) -> Any:
        return self.com.SketchManager

    @property
    def selection_manager(self) -> Any:
        return self.com.SelectionManager

    def create_select_data(self, *, mark: int = 0) -> Any:
        data = member_value(self.selection_manager, "CreateSelectData")
        data.Mark = int(mark)
        return data

    def __repr__(self) -> str:
        try:
            return f"ModelDoc(title={self.title!r})"
        except Exception:
            return "ModelDoc(<unreadable>)"

    def set_contour_selection(self, enabled: bool = True) -> None:
        self.selection_manager.EnableContourSelection = bool(enabled)

    def active_sketch(self, *, require: bool = True) -> Any:
        sketch = getattr(self.sketch_manager, "ActiveSketch", None)
        sketch = call_or_value(sketch) if sketch is not None else None
        if sketch is None:
            sketch = member_value(self.com, "GetActiveSketch2", None)
        if sketch is None and require:
            raise SolidWorksError("No active sketch")
        return sketch

    def active_sketch_contours(self, *, require: bool = True) -> list[SketchContour]:
        sketch = self.active_sketch(require=require)
        if sketch is None:
            return []
        return SketchContour.from_sketch(self, sketch)

    def activate(self) -> ModelDoc:
        if self.app is None:
            raise SolidWorksError("Cannot activate document without a SolidWorks application wrapper")
        errors = int_byref()
        try:
            result = self.app.com.ActivateDoc3(self.title, False, 0, errors)
        except TypeError:
            result = self.app.com.ActivateDoc3(self.title, False, 0, 0)
        err = int(result[1]) if isinstance(result, tuple) and len(result) > 1 else int(getattr(errors, "value", 0) or 0)
        if err:
            raise SolidWorksError(f"Failed to activate document: {self.title}", errors=err)
        return self

    def rebuild(self) -> None:
        ok = call_member(self.com, "EditRebuild3", default=None)
        if ok is False:
            raise SolidWorksError(f"Failed to rebuild document: {self.title}")

    def clear_selection(self, notify: bool = True) -> None:
        call_member(self.com, "ClearSelection2", bool(notify))

    def delete_selected(self) -> Any:
        return call_member(self.com, "EditDelete", default=None)

    def suppress_selected(self) -> Any:
        return call_member(self.com, "EditSuppress2", default=None)

    def unsuppress_selected(self) -> Any:
        return call_member(self.com, "EditUnsuppress2", default=None)

    def edit_selected_sketch(self) -> Any:
        return call_member(self.com, "EditSketch", default=None)

    def force_rebuild(self, top_only: bool = False) -> Any:
        return call_member(self.com, "ForceRebuild3", bool(top_only), default=None)

    def select_by_id(
        self,
        name: str,
        object_type: str,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        append: bool = False,
        mark: int = 0,
        callout: Any = None,
        options: int = 0,
        require: bool = True,
    ) -> bool:
        if callout is None:
            callout = empty_dispatch()
        selected = bool(self.extension.SelectByID2(name, object_type, x, y, z, append, mark, callout, options))
        if require and not selected:
            raise SolidWorksError(f"Failed to select {object_type}: {name}")
        return selected

    def select_by_ray(
        self,
        origin: Point | tuple[float, float, float],
        direction: Point | tuple[float, float, float],
        *,
        radius: float,
        select_type: int | SelectType,
        append: bool = False,
        mark: int = 0,
        options: int = 0,
        require: bool = True,
    ) -> bool:
        ox, oy, oz = _xyz(origin)
        dx, dy, dz = _xyz(direction)
        selected = bool(
            self.extension.SelectByRay(
                ox,
                oy,
                oz,
                dx,
                dy,
                dz,
                float(radius),
                int(select_type),
                bool(append),
                int(mark),
                int(options),
            )
        )
        if require and not selected:
            raise SolidWorksError(f"Failed to select entity by ray: type {int(select_type)}")
        return selected

    def select_face_by_ray(
        self,
        origin: Point | tuple[float, float, float],
        direction: Point | tuple[float, float, float],
        *,
        radius: float,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> bool:
        return self.select_by_ray(
            origin, direction, radius=radius, select_type=SelectType.Faces, append=append, mark=mark, require=require
        )

    def select_edge_by_ray(
        self,
        origin: Point | tuple[float, float, float],
        direction: Point | tuple[float, float, float],
        *,
        radius: float,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> bool:
        return self.select_by_ray(
            origin, direction, radius=radius, select_type=SelectType.Edges, append=append, mark=mark, require=require
        )

    def selected_object(self, index: int = 1, mark: int = -1, *, require: bool = True) -> Any:
        getter = getattr(self.selection_manager, "GetSelectedObject6", None)
        if not callable(getter):
            raise SolidWorksError("SelectionManager does not support GetSelectedObject6")
        obj = getter(int(index), int(mark))
        if obj is None and require:
            raise SolidWorksError(f"No selected object at index {index} with mark {mark}")
        return obj

    def select_plane(self, name: str, *, append: bool = False) -> bool:
        aliases = {
            "Top Plane": ("Top Plane", "上视基准面", "上基准面"),
            "Front Plane": ("Front Plane", "前视基准面", "前基准面"),
            "Right Plane": ("Right Plane", "右视基准面", "右基准面"),
        }
        for candidate in aliases.get(name, (name,)):
            if self.select_by_id(candidate, "PLANE", append=append, require=False):
                return True
        raise SolidWorksError(f"Failed to select PLANE: {name}")

    def select_feature(self, name: str, *, append: bool = False, mark: int = 0) -> bool:
        return self.select_by_id(name, "BODYFEATURE", append=append, mark=mark)

    def select_axis(self, name: str, *, append: bool = False, mark: int = 0) -> bool:
        return self.select_by_id(name, "AXIS", append=append, mark=mark)

    def select_sketch(self, name: str, *, append: bool = False, mark: int = 0) -> bool:
        return self.select_by_id(name, "SKETCH", append=append, mark=mark)

    def select_object(self, obj: Any, *, append: bool = False, mark: int = 0, require: bool = True) -> bool:
        select4 = getattr(obj, "Select4", None)
        if callable(select4):
            try:
                selected = bool(select4(bool(append), self.create_select_data(mark=mark)))
            except TypeError:
                selected = bool(select4(bool(append), None, int(mark)))
            if require and not selected:
                name = getattr(obj, "Name", repr(obj))
                raise SolidWorksError(f"Failed to select object: {name}")
            return selected
        select2 = getattr(obj, "Select2", None)
        if not callable(select2):
            raise SolidWorksError(f"Object does not support Select2: {obj!r}")
        selected = bool(select2(bool(append), int(mark)))
        if require and not selected:
            name = getattr(obj, "Name", repr(obj))
            raise SolidWorksError(f"Failed to select object: {name}")
        return selected

    def insert_axis_from_planes(
        self, plane_a: str, plane_b: str, *, name: str = "Reference Axis", auto_size: bool = True
    ) -> Any:
        self.clear_selection()
        self.select_plane(plane_a)
        self.select_plane(plane_b, append=True)
        ok = bool(self.com.InsertAxis2(bool(auto_size)))
        if not ok:
            raise SolidWorksError(f"Failed to create reference axis from planes: {plane_a}, {plane_b}")
        feature = self.last_feature()
        feature.Name = name
        return feature

    def select_sketch_contours(
        self,
        contours: list[SketchContour] | tuple[SketchContour, ...],
        *,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> int:
        self.set_contour_selection(True)
        selected = 0
        for index, contour in enumerate(contours):
            if contour.select(append=append or index > 0, mark=mark, require=require):
                selected += 1
        return selected

    def select_closed_sketch_contours(
        self,
        *,
        append: bool = False,
        mark: int = 0,
        min_segments: int = 0,
        require: bool = True,
    ) -> list[SketchContour]:
        contours = [
            contour
            for contour in self.active_sketch_contours()
            if contour.is_closed and contour.segment_count >= min_segments
        ]
        if require and not contours:
            raise SolidWorksError("No closed sketch contours found")
        self.select_sketch_contours(contours, append=append, mark=mark, require=require)
        return contours

    def select_matching_sketch_contours(
        self,
        predicate: ContourPredicate,
        *,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> list[SketchContour]:
        contours = [contour for contour in self.active_sketch_contours() if predicate(contour)]
        if require and not contours:
            raise SolidWorksError("No matching sketch contours found")
        self.select_sketch_contours(contours, append=append, mark=mark, require=require)
        return contours

    def last_feature(self) -> Any:
        feature = call_member(self.com, "FeatureByPositionReverse", 0, default=None)
        if feature is None:
            raise SolidWorksError("No feature exists in the current document")
        return feature

    def iter_features(self) -> Iterator[Any]:
        feature = member_value(self.com, "FirstFeature", None)
        while feature is not None:
            yield feature
            feature = member_value(feature, "GetNextFeature", None)

    def feature_name(self, feature: Any) -> str:
        return str(member_value(feature, "Name", ""))

    def feature_type(self, feature: Any) -> str:
        return str(member_value(feature, "GetTypeName2", ""))

    def find_feature(
        self,
        predicate: FeaturePredicate,
        *,
        after: Any | None = None,
        require: bool = True,
    ) -> Any | None:
        found_after = after is None
        for feature in self.iter_features():
            if not found_after:
                if _same_com_object(feature, after):
                    found_after = True
                continue
            if predicate(feature):
                return feature
        if require:
            raise SolidWorksError("No matching feature found")
        return None

    def find_features_by_name(
        self,
        name: str,
        *,
        type_name: str | None = None,
        contains: bool = False,
        case_sensitive: bool = True,
        after: Any | None = None,
    ) -> list[Any]:
        needle = str(name)
        if not case_sensitive:
            needle = needle.casefold()

        def matches(feature: Any) -> bool:
            if type_name is not None and self.feature_type(feature) != type_name:
                return False
            candidate = self.feature_name(feature)
            haystack = candidate if case_sensitive else candidate.casefold()
            return needle in haystack if contains else haystack == needle

        found_after = after is None
        matches_list: list[Any] = []
        for feature in self.iter_features():
            if not found_after:
                if _same_com_object(feature, after):
                    found_after = True
                continue
            if matches(feature):
                matches_list.append(feature)
        return matches_list

    def find_feature_by_name(
        self,
        name: str,
        *,
        type_name: str | None = None,
        contains: bool = False,
        case_sensitive: bool = True,
        after: Any | None = None,
        require: bool = True,
    ) -> Any | None:
        matches = self.find_features_by_name(
            name,
            type_name=type_name,
            contains=contains,
            case_sensitive=case_sensitive,
            after=after,
        )
        if matches:
            return matches[0]
        if require:
            raise SolidWorksError(f"No feature found matching name: {name!r}")
        return None

    def find_features_by_name_pattern(
        self,
        pattern: str,
        *,
        type_name: str | None = None,
        flags: int = 0,
        after: Any | None = None,
    ) -> list[Any]:
        regex = re.compile(pattern, flags)
        found_after = after is None
        matches: list[Any] = []
        for feature in self.iter_features():
            if not found_after:
                if _same_com_object(feature, after):
                    found_after = True
                continue
            if type_name is not None and self.feature_type(feature) != type_name:
                continue
            if regex.search(self.feature_name(feature)):
                matches.append(feature)
        return matches

    def select_feature_object(
        self,
        feature: Any,
        *,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> bool:
        return self.select_object(feature, append=append, mark=mark, require=require)

    def select_feature_by_name(
        self,
        name: str,
        *,
        type_name: str | None = None,
        contains: bool = False,
        case_sensitive: bool = True,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> bool:
        feature = self.find_feature_by_name(
            name,
            type_name=type_name,
            contains=contains,
            case_sensitive=case_sensitive,
            require=require,
        )
        if feature is None:
            return False
        return self.select_feature_object(feature, append=append, mark=mark, require=require)

    def next_feature(
        self,
        feature: Any,
        *,
        type_name: str | None = None,
        require: bool = True,
    ) -> Any | None:
        return self.find_feature(
            lambda candidate: type_name is None or self.feature_type(candidate) == type_name,
            after=feature,
            require=require,
        )

    def feature_error_code(self, feature: Any) -> int:
        try:
            return int(call_member(feature, "GetErrorCode", default=0) or 0)
        except Exception:
            return 0

    def feature_errors(self) -> list[tuple[Any, int]]:
        errors: list[tuple[Any, int]] = []
        for feature in self.iter_features():
            error = self.feature_error_code(feature)
            if error:
                errors.append((feature, error))
        return errors

    @property
    def feature_manager(self) -> Any:
        return self.com.FeatureManager

    def rollback(
        self,
        location: int | MoveRollbackBarTo,
        feature: Any | str = "",
        *,
        require: bool = True,
    ) -> bool:
        name = feature if isinstance(feature, str) else self.feature_name(feature)
        ok = bool(call_member(self.feature_manager, "EditRollback", int(location), str(name), default=False))
        if require and not ok:
            raise SolidWorksError(f"Failed to move rollback bar to {int(location)} for feature {name!r}")
        return ok

    def rollback_before(self, feature: Any | str, *, require: bool = True) -> bool:
        return self.rollback(MoveRollbackBarTo.BeforeFeature, feature, require=require)

    def rollback_after(self, feature: Any | str, *, require: bool = True) -> bool:
        return self.rollback(MoveRollbackBarTo.AfterFeature, feature, require=require)

    def rollback_to_end(self, *, require: bool = True) -> bool:
        return self.rollback(MoveRollbackBarTo.End, "", require=require)

    def suppress_feature(self, feature: Any) -> Any:
        self.clear_selection()
        self.select_object(feature)
        return self.suppress_selected()

    def unsuppress_feature(self, feature: Any) -> Any:
        self.clear_selection()
        self.select_object(feature)
        return self.unsuppress_selected()

    def delete_feature(self, feature: Any) -> Any:
        self.clear_selection()
        self.select_object(feature)
        return self.delete_selected()

    def part_box(self, *, exact: bool = True) -> tuple[float, float, float, float, float, float]:
        box = call_member(self.com, "GetPartBox", bool(exact), default=None)
        if box is None:
            raise SolidWorksError("Active document does not expose GetPartBox")
        values = tuple(float(value) for value in list(box)[:6])
        if len(values) != 6:
            raise SolidWorksError("GetPartBox returned an invalid bounding box")
        return values

    def size(self, *, exact: bool = True) -> tuple[float, float, float]:
        xmin, ymin, zmin, xmax, ymax, zmax = self.part_box(exact=exact)
        return xmax - xmin, ymax - ymin, zmax - zmin

    def rename_last_feature(self, name: str) -> Any:
        feature = self.last_feature()
        feature.Name = name
        return feature

    @contextmanager
    def sketch(self) -> Iterator[SketchBuilder]:
        self.sketch_manager.InsertSketch(True)
        try:
            yield SketchBuilder(self)
        finally:
            self.sketch_manager.InsertSketch(True)

    @contextmanager
    def sketch_on_face_at(
        self, x: float, y: float, z: float
    ) -> Iterator[SketchBuilder]:
        """Open a 2D sketch on a body face at the given global coordinates.

        Unlike :py:meth:`sketch` (which uses a reference plane), this
        uses a real body face as the sketch plane. This is the only
        way to add a cut/extrude to a body whose relevant face does
        not coincide with a reference plane (e.g., a U-fork body
        whose prongs are open at the top, so the Top Plane does not
        match a single body face).

        ``(x, y, z)`` must be a point that lies on the target face in
        global coordinates; SOLIDWORKS finds the closest face.
        """
        self.clear_selection()
        ok = bool(
            self.com.Extension.SelectByID2(
                "", "FACE", float(x), float(y), float(z), False, 0, empty_dispatch(), 0
            )
        )
        if not ok:
            raise SolidWorksError(
                f"Failed to select FACE at global ({x}, {y}, {z})"
            )
        # Open the 2D sketch on the selected face (mirrors sketch()).
        self.sketch_manager.InsertSketch(True)
        try:
            yield SketchBuilder(self)
        finally:
            self.sketch_manager.InsertSketch(True)

    @contextmanager
    def sketch3d(self) -> Iterator[SketchBuilder]:
        self.sketch_manager.Insert3DSketch(True)
        try:
            yield SketchBuilder(self)
        finally:
            self.sketch_manager.Insert3DSketch(True)

    @contextmanager
    def edit_sketch_feature(self, feature: Any) -> Iterator[SketchEditor]:
        self.clear_selection()
        self.select_object(feature)
        self.edit_selected_sketch()

        try:
            yield SketchEditor(self, feature)
        finally:
            self.clear_selection()
            self.edit_selected_sketch()

    def find_face_at(self, x: float, y: float, z: float, *, require: bool = True) -> Any:
        """Return the body face closest to global coordinates ``(x, y, z)``.
        Uses SOLIDWORKS ``SelectByID2`` with empty name and type
        ``"FACE"`` to find the nearest face, then returns the
        selected face object. This is the prerequisite for face-based
        boolean cuts (see :pymeth:`bool_subtract`).
        """
        self.clear_selection()
        ok = self.select_by_id("", "FACE", x=x, y=y, z=z, require=False)
        if not ok:
            if require:
                raise SolidWorksError(
                    f"Failed to find a body FACE at global ({x}, {y}, {z})"
                )
            return None
        return self.selected_object(1, require=require)
    def extrude_cylinder(
        self,
        face: Any,
        center: tuple[float, float],
        radius: float,
        depth: float,
        *,
        reverse: bool = False,
    ) -> Any:
        """Sketch a circle on ``face`` and extrude it as a separate body.
        The new cylinder body is *not* merged with the existing body
        (``merge=False``), so it can be used as a cutter in
        :pymeth:`bool_subtract`. ``center`` is in the face's local
        2D coordinates. ``depth`` is the extrude depth in metres.
        ``reverse=True`` extrudes in the face's opposite-normal
        direction.
        """
        # The face's global position is the centre of the face plane;
        # we open a sketch on it via sketch_on_face_at using any point
        # on the face. We use the face's GetCenter or fall back to
        # SelectByID2 with the face's centroid.
        self.clear_selection()
        # Pick any 3D point on the face by re-selecting it. SOLIDWORKS
        # provides a face's box bounds, but the cheapest reliable path
        # is to ask the caller to pass a point; if the caller already
        # has the face, they typically also know a point on it. We
        # just re-select by id.
        # For simplicity, callers should pre-position by passing a
        # point that lies on the face; we use the face's bounding
        # box centre.
        cx, cy, cz = _face_centroid(face)
        with self.sketch_on_face_at(cx, cy, cz) as sk:
            sk.circle(float(center[0]), float(center[1]), float(radius))
        # The just-closed sketch is the active one. Use extrude_blind
        # with merge=False so a new body is created.
        feature = self.features.extrude_blind(
            float(depth), merge=False, reverse=bool(reverse)
        )
        if feature is None:
            raise SolidWorksError(
                "Failed to extrude cylinder (FeatureExtrusion3 returned None)"
            )
        # Return the body that was created. After an unmerged extrude
        # the active body is the new one; the caller can use it for
        # boolean operations.
        return self.active_body()

    def bool_subtract(
        self,
        target_body: Any,
        tool_body: Any,
        *,
        keep_tool: bool = False,
    ) -> Any:
        """Boolean-subtract ``tool_body`` from ``target_body``.
        Returns the new combined target body (or the combined feature).
        ``keep_tool=True`` keeps the tool body in the part after the
        cut (rarely useful; default False deletes the cutter).
        """
        # SOLIDWORKS: select target body, then select tool body, then
        # call InsertCutFeature on the tool body.
        self.clear_selection()
        self.select_object(target_body, mark=1)
        # Append the tool body to the selection list (mark 0)
        self.select_object(tool_body, append=True, mark=0)
        feature = self.extension.InsertCutFeature(
            tool_body, bool(keep_tool)
        )
        if feature is None:
            raise SolidWorksError("Boolean subtract returned no feature")
        return feature

    def make_hole(
        self,
        target_body: Any,
        face: Any,
        center: tuple[float, float],
        radius: float,
        depth: float,
        *,
        reverse: bool = False,
    ) -> Any:
        """Convenience: cut a cylindrical hole through ``target_body``.
        1. Creates a cylinder cutter body on ``face`` at ``center``
           (face-local 2D coordinates) using :pymeth:`extrude_cylinder`.
        2. Subtracts the cutter from ``target_body`` using
           :pymeth:`bool_subtract` (tool body deleted after cut).

        Returns the new combined target body.
        """
        cutter = self.extrude_cylinder(
            face, center=center, radius=radius, depth=depth, reverse=reverse
        )
        return self.bool_subtract(target_body, cutter, keep_tool=False)

    def bodies(self) -> list[Any]:
        """Return all bodies in the active part as a list."""
        result: list[Any] = []
        try:
            result = _as_list(call_or_value(lambda: self.com.GetBodies(0)))
        except Exception:
            return result
        return result

    def active_body(self) -> Any:
        """Return the most recently created body in the active part.
        :pymeth:`extrude_cylinder`) SOLIDWORKS activates the new body.
        This helper returns that body so the caller can chain it
        into a boolean operation. Falls back to the first body if no
        active body is detectable.
        """
        all_bodies = self.bodies()
        if not all_bodies:
            return None
        return all_bodies[-1]

    @contextmanager
    def replace_feature_at_history(
        self,
        old_feature: Any,
        *,
        delete_old_on_success: bool = False,
        rebuild: bool = True,
    ) -> Iterator[Any]:
        self.suppress_feature(old_feature)
        if rebuild:
            self.rebuild()
        self.rollback_before(old_feature)
        try:
            yield old_feature
            self.rollback_to_end()
            self.force_rebuild(False)
            self.rebuild()
            errors = self.feature_errors()
            if errors:
                details = ", ".join(f"{self.feature_name(feature)}={error}" for feature, error in errors)
                raise SolidWorksError(f"Feature replacement left rebuild errors: {details}")
            if delete_old_on_success:
                self.delete_feature(old_feature)
                self.force_rebuild(False)
                self.rebuild()
        except Exception:
            self.rollback_to_end(require=False)
            raise

    def save(self) -> None:
        """Save the current document.

        Automatically activates the document and clears selection before saving
        to ensure the save operation succeeds.
        """
        self.activate()
        self.clear_selection()
        errors = int_byref()
        warnings = int_byref()
        result = self.com.Save3(int(SaveAsOptions.Silent), errors, warnings)
        out = unpack_out_call(result, errors, warnings)
        if not bool(out.value):
            raise SolidWorksError(
                f"Failed to save document: {self.title}",
                errors=out.errors,
                warnings=out.warnings,
            )

    def save_as(
        self,
        path: str | Path,
        *,
        version: int | SaveAsVersion = SaveAsVersion.CurrentVersion,
        options: int | SaveAsOptions = SaveAsOptions.Silent,
        export_data: Any = None,
        advanced_options: Any = None,
    ) -> None:
        """Save the document to a new path.

        Automatically activates the document and clears selection before saving
        to ensure the save operation succeeds.

        Args:
            path: Destination file path.
            version: SOLIDWORKS version to save as (default: current).
            options: Save options (default: Silent).
            export_data: Optional export data for specialized formats.
            advanced_options: Optional advanced save options.
        """
        self.activate()
        self.clear_selection()
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        errors = int_byref()
        warnings = int_byref()
        if export_data is None:
            export_data = empty_dispatch()
        if advanced_options is None:
            advanced_options = empty_dispatch()
        if hasattr(self.extension, "SaveAs3"):
            result = self.extension.SaveAs3(
                str(path), int(version), int(options), export_data, advanced_options, errors, warnings
            )
        else:
            result = self.extension.SaveAs(str(path), int(version), int(options), export_data, errors, warnings)
        out = unpack_out_call(result, errors, warnings)
        if not bool(out.value):
            raise SolidWorksError(
                f"Failed to save document as: {path}",
                errors=out.errors,
                warnings=out.warnings,
            )

    def export(self, path: str | Path, *, options: int | SaveAsOptions = SaveAsOptions.Silent) -> None:
        """Export the document to a different format (e.g., STEP, IGES).

        This is a convenience wrapper around :meth:`save_as` that is
        semantically clearer when converting between formats.
        """
        self.save_as(path, options=options)

    def save_and_export(
        self,
        sldprt_path: str | Path,
        export_path: str | Path,
        *,
        export_options: int | SaveAsOptions = SaveAsOptions.Silent,
    ) -> tuple[Path, Path]:
        """Save as SLDPRT and export to another format in one call.

        This is the recommended pattern for saving a native SOLIDWORKS file
        and exporting a STEP/IGES/etc. copy in the same operation.

        Args:
            sldprt_path: Path for the native .SLDPRT file.
            export_path: Path for the export file (e.g., .step, .iges).
            export_options: Options for the export operation.

        Returns:
            Tuple of (sldprt_path, export_path) as resolved Path objects.
        """
        sldprt = Path(sldprt_path)
        export = Path(export_path)
        self.save_as(sldprt)
        self.export(export, options=export_options)
        return sldprt, export

    def builder(self) -> Any:
        from .builders import PartBuilder

        return PartBuilder(self)

    @property
    def inspector(self) -> Any:
        """Get a ModelInspector for geometry inspection and validation.

        Returns:
            ModelInspector instance for this model.

        Example::

            report = part.inspector.inspect()
            print(report.summary())

            # Validate specific dimensions
            report = part.inspector.validate_model(
                expected_width=mm(100),
                expected_height=mm(50),
            )
            if report.has_errors:
                print(report.summary())
        """
        from .inspection import ModelInspector

        return ModelInspector(self)

    @property
    def parameters(self) -> Any:
        """Get or create a ParameterManager for this model.

        Returns:
            ParameterManager instance for managing model parameters.

        Example::

            # Add parameters
            part.parameters.add("width", mm(100), description="Part width")
            part.parameters.add("height", mm(50), description="Part height")

            # Add derived parameter
            part.parameters.add_derived(
                "area",
                lambda: part.parameters.get_value("width") * part.parameters.get_value("height"),
                unit="mm²",
            )

            # Update parameter
            part.parameters.update("width", mm(120))
        """
        if not hasattr(self, '_parameters'):
            from .parameters import ParameterManager
            self._parameters = ParameterManager()
        return self._parameters

    @property
    def analyzer(self) -> Any:
        """Get a GeometryAnalyzer for extracting geometry facts.

        Returns:
            GeometryAnalyzer instance for this model.

        Example::

            facts = part.analyzer.extract_facts()
            print(f"Size: {facts.size}")
            print(f"Center: {facts.center}")
            print(f"Extent axis: {facts.extent_axis}")
        """
        from .analysis import GeometryAnalyzer

        return GeometryAnalyzer(self)

    @property
    def metadata_manager(self) -> Any:
        """Get a MetadataManager for tracking generation metadata.

        Returns:
            MetadataManager instance for this model.

        Example::

            part.metadata_manager.record_source("examples/model.py")
            part.metadata_manager.record_generation(generator_name="solidworks-com")
            part.metadata_manager.record_output("output/model.SLDPRT")
            part.metadata_manager.save("output/model.metadata.json")
        """
        if not hasattr(self, '_metadata_manager'):
            from .metadata import MetadataManager
            self._metadata_manager = MetadataManager(self)
        return self._metadata_manager

    @property
    def export_manager(self) -> Any:
        """Get an ExportManager for multi-format export.

        Returns:
            ExportManager instance for this model.

        Example::

            # Export to single format
            result = part.export_manager.export("step", "output/model.step")

            # Export to multiple formats
            results = part.export_manager.export_multiple(
                ["step", "stl", "3mf"],
                "output/"
            )
        """
        if not hasattr(self, '_export_manager'):
            from .export import ExportManager
            self._export_manager = ExportManager(self)
        return self._export_manager


class SketchBuilder:
    def __init__(self, model: ModelDoc) -> None:
        self.model = model

    @property
    def com(self) -> Any:
        return self.model.sketch_manager

    def line(self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> Any:
        return self.com.CreateLine(x1, y1, z1, x2, y2, z2)

    def centerline(self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> Any:
        return self.com.CreateCenterLine(x1, y1, z1, x2, y2, z2)

    def corner_rectangle(self, x1: float, y1: float, x2: float, y2: float, *, z: float = 0.0) -> Any:
        return self.com.CreateCornerRectangle(x1, y1, z, x2, y2, z)

    def center_rectangle(self, cx: float, cy: float, corner_x: float, corner_y: float, *, z: float = 0.0) -> Any:
        return self.com.CreateCenterRectangle(cx, cy, z, corner_x, corner_y, z)

    def circle(self, cx: float, cy: float, radius: float, *, z: float = 0.0) -> Any:
        return self.com.CreateCircleByRadius(cx, cy, z, radius)

    def arc(
        self, cx: float, cy: float, sx: float, sy: float, ex: float, ey: float, *, z: float = 0.0, direction: int = 1
    ) -> Any:
        return self.com.CreateArc(cx, cy, z, sx, sy, z, ex, ey, z, direction)

    def three_point_arc(
        self, sx: float, sy: float, ex: float, ey: float, mx: float, my: float, *, z: float = 0.0
    ) -> Any:
        return self.com.Create3PointArc(sx, sy, z, ex, ey, z, mx, my, z)

    def ellipse(
        self,
        cx: float,
        cy: float,
        major_x: float,
        major_y: float,
        minor_x: float,
        minor_y: float,
        *,
        z: float = 0.0,
    ) -> Any:
        return self.com.CreateEllipse(cx, cy, z, major_x, major_y, z, minor_x, minor_y, z)

    def polygon(
        self,
        cx: float,
        cy: float,
        vertex_x: float,
        vertex_y: float,
        *,
        sides: int,
        inscribed: bool = True,
        z: float = 0.0,
    ) -> Any:
        return self.com.CreatePolygon(cx, cy, z, vertex_x, vertex_y, z, int(sides), bool(inscribed))

    def spline(
        self, points: list[Point | tuple[float, float] | tuple[float, float, float]], *, closed: bool = False
    ) -> Any:
        data = double_array(flatten_points(points))
        create_spline3 = getattr(self.com, "CreateSpline3", None)
        if callable(create_spline3):
            status = variant_byref()
            segment = create_spline3(data, empty_variant(), empty_variant(), bool(closed), status)
            if segment is not None:
                return segment
        create_spline2 = getattr(self.com, "CreateSpline2", None)
        if callable(create_spline2):
            segment = create_spline2(data, bool(closed))
            if segment is not None:
                return segment
        create_spline = getattr(self.com, "CreateSpline", None)
        if callable(create_spline):
            segment = create_spline(data)
            if segment is not None:
                return segment
        raise SolidWorksError("Failed to create sketch spline")

    def equation_spline(
        self,
        x_expression: str,
        y_expression: str,
        *,
        z_expression: str = "",
        range_start: str,
        range_end: str,
        is_angle_range: bool = False,
        rotation_angle: float = 0.0,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        lock_start: bool = True,
        lock_end: bool = True,
    ) -> Any:
        create_equation_spline2 = getattr(self.com, "CreateEquationSpline2", None)
        if callable(create_equation_spline2):
            segment = create_equation_spline2(
                str(x_expression),
                str(y_expression),
                str(z_expression),
                str(range_start),
                str(range_end),
                bool(is_angle_range),
                float(rotation_angle),
                float(x_offset),
                float(y_offset),
                bool(lock_start),
                bool(lock_end),
            )
            if segment is not None:
                return segment
        create_equation_spline = getattr(self.com, "CreateEquationSpline", None)
        if callable(create_equation_spline) and not x_expression and not z_expression:
            segment = create_equation_spline(
                str(y_expression),
                str(range_start),
                str(range_end),
                bool(is_angle_range),
                float(rotation_angle),
                float(x_offset),
                float(y_offset),
                bool(lock_start),
                bool(lock_end),
            )
            if segment is not None:
                return segment
        raise SolidWorksError("Failed to create equation-driven sketch spline")

    def polyline(
        self, points: list[Point | tuple[float, float] | tuple[float, float, float]], *, close: bool = True
    ) -> list[Any]:
        if len(points) < 2:
            raise ValueError("polyline requires at least two points")
        normalized = [
            p if isinstance(p, Point) else Point(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)
            for p in points
        ]
        if close and normalized[0] != normalized[-1]:
            normalized.append(normalized[0])
        return [self.line(a.x, a.y, a.z, b.x, b.y, b.z) for a, b in zip(normalized, normalized[1:])]

    @property
    def active_sketch(self) -> Any:
        return self.model.active_sketch()

    @property
    def relation_manager(self) -> Any:
        sketch = self.active_sketch
        manager = getattr(sketch, "RelationManager", None)
        if manager is None:
            raise SolidWorksError("Active sketch does not expose RelationManager")
        return manager

    def add_relation(self, entities: list[Any] | tuple[Any, ...], relation_type: int | ConstraintType) -> Any:
        if not entities:
            raise ValueError("add_relation requires at least one entity")
        constraint = (
            ConstraintType(int(relation_type)) if int(relation_type) in _SKETCH_CONSTRAINT_NAMES else relation_type
        )
        if constraint in _SKETCH_CONSTRAINT_NAMES:
            return self.add_constraint_to_selected_entities(entities, constraint)
        relation = self.relation_manager.AddRelation(variant_array(tuple(entities)), int(relation_type))
        if relation is None:
            raise SolidWorksError(f"Failed to add sketch relation: {int(relation_type)}")
        return relation

    def add_constraint_to_selected_entities(
        self, entities: list[Any] | tuple[Any, ...], relation_type: int | ConstraintType
    ) -> None:
        constraint_name = _SKETCH_CONSTRAINT_NAMES.get(ConstraintType(int(relation_type)))
        if constraint_name is None:
            raise SolidWorksError(f"SketchAddConstraints does not support relation: {int(relation_type)}")
        self.model.clear_selection()
        for index, entity in enumerate(entities):
            self.model.select_object(entity, append=index > 0)
        self.model.com.SketchAddConstraints(constraint_name)
        self.model.clear_selection()

    def coincident(self, entity_a: Any, entity_b: Any) -> Any:
        return self.add_relation((entity_a, entity_b), ConstraintType.Coincident)

    def tangent(self, entity_a: Any, entity_b: Any) -> Any:
        return self.add_relation((entity_a, entity_b), ConstraintType.Tangent)

    def merge_points(self, point_a: Any, point_b: Any) -> Any:
        return self.add_relation((point_a, point_b), ConstraintType.MergePoints)

    def start_point(self, segment: Any) -> Any:
        return sketch_segment_endpoint(segment, start=True)

    def end_point(self, segment: Any) -> Any:
        return sketch_segment_endpoint(segment, start=False)

    def coincident_endpoints(
        self, segment_a: Any, segment_b: Any, *, a_start: bool = False, b_start: bool = True
    ) -> Any:
        point_a = sketch_segment_endpoint(segment_a, start=a_start)
        point_b = sketch_segment_endpoint(segment_b, start=b_start)
        return self.coincident(point_a, point_b)

    def contours(self, *, require: bool = True) -> list[SketchContour]:
        return self.model.active_sketch_contours(require=require)

    def select_closed_contours(
        self, *, append: bool = False, mark: int = 0, min_segments: int = 0
    ) -> list[SketchContour]:
        return self.model.select_closed_sketch_contours(append=append, mark=mark, min_segments=min_segments)


class SketchEditor:
    def __init__(self, model: ModelDoc, feature: Any) -> None:
        self.model = model
        self.feature = feature

    @property
    def com(self) -> Any:
        return self.model.active_sketch()

    def segments(self) -> list[SketchSegment]:
        return [
            SketchSegment(self.model, segment) for segment in _as_list(member_value(self.com, "GetSketchSegments", []))
        ]

    def matching_segments(self, predicate: SegmentPredicate) -> list[SketchSegment]:
        return [segment for segment in self.segments() if predicate(segment)]

    def delete_segments(self, predicate: SegmentPredicate, *, max_iterations: int = 500) -> int:
        deleted = 0
        for _ in range(max_iterations):
            matches = self.matching_segments(predicate)
            if not matches:
                return deleted
            matches[0].delete()
            deleted += 1  # noqa: SIM113 — counts deletions, not iterations
        raise SolidWorksError(
            f"delete_segments exceeded {max_iterations} iterations — "
            "a deleted segment may not have been removed from the sketch"
        )

    def contours(self) -> list[SketchContour]:
        return SketchContour.from_sketch(self.model, self.com)

    def matching_contours(self, predicate: ContourPredicate) -> list[SketchContour]:
        return [contour for contour in self.contours() if predicate(contour)]

    def select_contours(
        self,
        contours: list[SketchContour] | tuple[SketchContour, ...],
        *,
        append: bool = False,
        mark: int = 0,
        require: bool = True,
    ) -> int:
        return self.model.select_sketch_contours(contours, append=append, mark=mark, require=require)


class SketchContour:
    def __init__(self, model: ModelDoc, com: Any) -> None:
        self.model = model
        self.com = com

    @staticmethod
    def from_sketch(model: ModelDoc, sketch: Any) -> list[SketchContour]:
        contours = _as_list(member_value(sketch, "GetSketchContours"))
        return [SketchContour(model, contour) for contour in contours if contour is not None]

    @property
    def is_closed(self) -> bool:
        return bool(member_value(self.com, "IsClosed"))

    @property
    def segment_count(self) -> int:
        get_count = getattr(self.com, "GetSketchSegmentsCount", None)
        if get_count is not None:
            return int(call_or_value(get_count))
        return len(self.segments)

    @property
    def segments(self) -> list[Any]:
        return _as_list(member_value(self.com, "GetSketchSegments"))

    @property
    def sketch_segments(self) -> list[SketchSegment]:
        return [SketchSegment(self.model, segment) for segment in self.segments]

    @property
    def edge_count(self) -> int:
        get_count = getattr(self.com, "GetEdgesCount", None)
        if get_count is not None:
            return int(call_or_value(get_count))
        return len(self.edges)

    @property
    def edges(self) -> list[Any]:
        get_edges = getattr(self.com, "GetEdges", None)
        return _as_list(call_or_value(get_edges)) if get_edges is not None else []

    def select(self, *, append: bool = False, mark: int = 0, require: bool = True) -> bool:
        self.model.set_contour_selection(True)
        try:
            selected = bool(call_member(self.com, "Select2", bool(append), self.model.create_select_data(mark=mark)))
        except TypeError:
            selected = bool(call_member(self.com, "Select2", bool(append), int(mark)))
        if require and not selected:
            raise SolidWorksError("Failed to select sketch contour")
        return selected

    def deselect(self) -> None:
        call_member(self.com, "DeSelect", default=None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _xyz(value: Point | tuple[float, float, float]) -> tuple[float, float, float]:
    if isinstance(value, Point):
        return value.x, value.y, value.z
    return float(value[0]), float(value[1]), float(value[2])


def _face_centroid(face: Any) -> tuple[float, float, float]:
    """Return a 3D point on ``face`` (centre of its bounding box).

    For a planar face the bounding box centre is a valid point on the
    face; for curved faces it's an approximation but is good enough
    for the SOLIDWORKS ``SelectByID2`` proximity search.

    Note: we call ``face.GetBox()`` directly (not via
    ``call_or_value``) because the latter short-circuits on
    ``_oleobj_`` membership — auto-created by MagicMock in unit tests.
    """
    try:
        get_box = getattr(face, "GetBox", None)
        box = get_box() if callable(get_box) else get_box
        if box is None:
            return (0.0, 0.0, 0.0)
        # ``GetBox`` returns 6 doubles: xMin, yMin, zMin, xMax, yMax, zMax.
        vals = _as_list(box)
        if len(vals) >= 6:
            return (
                (vals[0] + vals[3]) / 2.0,
                (vals[1] + vals[4]) / 2.0,
                (vals[2] + vals[5]) / 2.0,
            )
    except Exception as exc:
        logger.debug("_face_centroid fallback (0,0,0): %s", exc)
    return (0.0, 0.0, 0.0)


def _body_centroid(body: Any) -> tuple[float, float, float]:
    """Return the centre of the body's bounding box."""
    try:
        get_box = getattr(body, "GetBodyBox", None)
        box = get_box() if callable(get_box) else get_box
        if box is None:
            return (0.0, 0.0, 0.0)
        vals = _as_list(box)
        if len(vals) >= 6:
            return (
                (vals[0] + vals[3]) / 2.0,
                (vals[1] + vals[4]) / 2.0,
                (vals[2] + vals[5]) / 2.0,
            )
    except Exception as exc:
        logger.debug("_body_centroid fallback (0,0,0): %s", exc)
    return (0.0, 0.0, 0.0)


def _same_com_object(left: Any, right: Any) -> bool:
    if left is right:
        return True
    try:
        return bool(left == right)
    except Exception:
        return False


_SKETCH_CONSTRAINT_NAMES = {
    ConstraintType.Horizontal: "sgHORIZONTAL2D",
    ConstraintType.Vertical: "sgVERTICAL2D",
    ConstraintType.Tangent: "sgTANGENT",
    ConstraintType.Parallel: "sgPARALLEL",
    ConstraintType.Perpendicular: "sgPERPENDICULAR",
    ConstraintType.Coincident: "sgCOINCIDENT",
    ConstraintType.Concentric: "sgCONCENTRIC",
    ConstraintType.Symmetric: "sgSYMMETRIC",
    ConstraintType.AtMiddle: "sgATMIDDLE",
    ConstraintType.AtIntersect: "sgATINTERSECT",
    ConstraintType.SameLength: "sgSAMELENGTH",
    ConstraintType.Fixed: "sgFIXED",
    ConstraintType.Colinear: "sgCOLINEAR",
    ConstraintType.Coradial: "sgCORADIAL",
    ConstraintType.MergePoints: "sgMERGEPOINTS",
}


def sketch_segment_endpoint(segment: Any, *, start: bool) -> Any:
    segment = _specific_sketch_segment(segment)
    method_name = "GetStartPoint2" if start else "GetEndPoint2"
    getter = getattr(segment, method_name, None)
    if getter is not None:
        try:
            point = call_or_value(getter)
            if point is not None:
                return point
        except Exception:
            pass
    get_points = getattr(segment, "GetPoints2", None)
    if get_points is not None:
        try:
            points = _as_list(call_or_value(get_points))
            if points:
                return points[0] if start else points[-1]
        except Exception:
            pass
    raise SolidWorksError(f"Sketch segment does not expose {'start' if start else 'end'} point")


def _specific_sketch_segment(segment: Any) -> Any:
    _, win32com_client = import_pywin32()
    for interface_name in ("SketchLine", "SketchArc", "SketchSpline"):
        try:
            return win32com_client.CastTo(segment, interface_name)
        except Exception:
            continue
    return segment


class FeatureTools:
    def __init__(self, model: ModelDoc) -> None:
        self.model = model

    @property
    def com(self) -> Any:
        return self.model.com.FeatureManager

    def extrude_blind(
        self,
        depth: float,
        *,
        reverse: bool = False,
        merge: bool = True,
        thin_feature: bool = False,
        flip: bool = False,
    ) -> Any:
        """Create a blind extrusion from the active sketch.

        Args:
            depth: Extrusion depth in meters.
            reverse: If True, reverse the extrusion direction.
            merge: If True, merge with existing body.
            thin_feature: If True, create a thin feature.
            flip: If True, flip the extrusion direction.
        """
        feature = self.com.FeatureExtrusion3(
            True,                   # sd (single direction) - MUST be True
            bool(flip),             # flip
            bool(reverse),          # dir (reverse direction)
            int(EndCondition.Blind),  # end condition 1
            int(EndCondition.Blind),  # end condition 2
            float(depth),           # depth 1
            0.0,                    # depth 2
            False,                  # draft 1
            False,                  # draft 2
            False,                  # draft outward 1
            False,                  # draft outward 2
            0.0,                    # draft angle 1
            0.0,                    # draft angle 2
            False,                  # offset reverse 1
            False,                  # offset reverse 2
            False,                  # translate surface 1
            False,                  # translate surface 2
            bool(merge),            # merge
            True,                   # use feature scope
            True,                   # auto select
            int(EndCondition.Blind),  # end condition 2 type
            0.0,                    # offset distance 2
            False,                  # offset reverse 2
        )
        if feature is None:
            raise SolidWorksError("Failed to create blind extrusion")
        return feature

    def extrude_midplane(self, depth: float, *, merge: bool = True, thin_feature: bool = False) -> Any:
        """Create a mid-plane extrusion from the active sketch."""
        feature = self.com.FeatureExtrusion3(
            True,                   # sd (single direction) - MUST be True
            False,                  # flip
            False,
            int(EndCondition.MidPlane),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(merge),
            True,
            True,
            int(EndCondition.Blind),
            0.0,
            False,
        )
        if feature is None:
            raise SolidWorksError("Failed to create mid-plane extrusion")
        return feature

    def cut_blind(self, depth: float, *, reverse: bool = False, normal_cut: bool = False) -> Any:
        """Create a blind cut from the active sketch."""
        feature = self.com.FeatureCut4(
            True,                   # sd (single direction) - MUST be True
            False,
            bool(reverse),
            int(EndCondition.Blind),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(normal_cut),
            True,
            True,
            False,
            True,
            False,
            int(EndCondition.Blind),
            0.0,
            False,
            True,
        )
        if feature is None:
            raise SolidWorksError("Failed to create blind cut")
        return feature

    def cut_midplane(self, depth: float, *, normal_cut: bool = False) -> Any:
        """Create a mid-plane cut from the active sketch."""
        feature = self.com.FeatureCut4(
            True,                   # sd (single direction) - MUST be True
            False,                  # flip
            False,
            int(EndCondition.MidPlane),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(normal_cut),
            True,
            True,
            False,
            True,
            False,
            int(EndCondition.Blind),
            0.0,
            False,
            True,
        )
        if feature is None:
            raise SolidWorksError("Failed to create mid-plane cut")
        return feature

    def revolve(
        self, *, angle: float | None = None, cut: bool = False, reverse: bool = False, merge: bool = True
    ) -> Any:
        """Create a revolve feature from the active sketch.

        The sketch must contain a closed profile. The revolve axis is
        automatically selected from the sketch's first centerline or
        the Y-axis of the sketch plane.

        Args:
            angle: Revolve angle in degrees (default 360).
            cut: If True, create a cut revolve.
            reverse: If True, reverse the revolve direction.
            merge: If True, merge with existing body.
        """
        # Try FeatureRevolve2 first (simpler API)
        angle_rad = deg(angle) if angle is not None else deg(360)
        feature = self.com.FeatureRevolve2(
            True,           # Single direction
            False,          # Not both directions
            False,          # Not thin feature
            bool(cut),      # Cut
            bool(reverse),  # Reverse
            False,          # Not thin feature
            int(EndCondition.Blind),  # End condition 1
            int(EndCondition.Blind),  # End condition 2
            float(angle_rad),         # Angle 1 (radians)
            0.0,                      # Angle 2
            False,          # Offset reverse 1
            False,          # Offset reverse 2
            0.0,            # Offset 1
            0.0,            # Offset 2
            0,              # Thin type
            0.0,            # Thin thickness 1
            0.0,            # Thin thickness 2
            bool(merge),    # Merge
            True,           # Use feature scope
            True,           # Auto select
        )
        if feature is None:
            raise SolidWorksError("Failed to create revolve feature")
        return feature

    def bool_union(self, body1: Any, body2: Any) -> Any:
        # v0.2: boolean-add two bodies via InsertCombineFeature.
        # Select both bodies (mark=1) and call the feature manager.
        # The operation type 0 is swCombineOperationType_Add.
        self.model.clear_selection()
        self.model.select_object(body1, mark=1)
        self.model.select_object(body2, append=True, mark=1)
        feature = self.com.FeatureManager.InsertCombineFeature(
            0,  # swCombineOperationType_Add
            body1,
            body2,
        )
        if feature is None:
            raise SolidWorksError("Failed to create boolean union")
        return feature

    def fillet_selected(self, radius: float, *, options: int = 0) -> Any:
        feature = self.com.FeatureFillet3(
            int(options), float(radius), 0.0, 0.0, 0, 0, 0, None, None, None, None, None, None, None
        )
        if feature is None:
            raise SolidWorksError("Failed to create fillet from selected entities")
        return feature

    def chamfer_selected(
        self,
        distance: float,
        *,
        chamfer_type: int | ChamferType = ChamferType.EqualDistance,
        options: int | ChamferOption = ChamferOption.NONE,
        angle: float = deg(45),
        other_distance: float = 0.0,
        vertex_distance_1: float = 0.0,
        vertex_distance_2: float = 0.0,
        vertex_distance_3: float = 0.0,
    ) -> Any:
        """Create a chamfer from the current edge selection.

        Args:
            distance: Primary chamfer distance in meters.
            chamfer_type: One of :class:`ChamferType`. The default
                ``EqualDistance`` interprets ``distance`` as the
                single equal offset on both faces.
            options: Bitfield of :class:`ChamferOption`.
            angle: Chamfer angle in radians. Used only when
                ``chamfer_type`` is :attr:`ChamferType.AngleDistance`.
            other_distance: Secondary distance (used by
                :attr:`ChamferType.DistanceDistance`).
            vertex_distance_1/2/3: Per-vertex distances (used by
                :attr:`ChamferType.Vertex`).

        SOLIDWORKS' ``InsertFeatureChamfer`` API requires edges to be
        selected first (``Edge`` or ``Feature`` selection). After
        selecting the edges with the appropriate mark, call this
        method to commit the chamfer.
        """
        feature = self.com.InsertFeatureChamfer(
            int(options),
            int(chamfer_type),
            float(distance),
            float(angle),
            float(other_distance),
            float(vertex_distance_1),
            float(vertex_distance_2),
            float(vertex_distance_3),
        )
        if feature is None:
            raise SolidWorksError("Failed to create chamfer from selected entities")
        return feature

    def circular_pattern_selected(
        self,
        instances: int,
        angle: float = deg(360),
        *,
        flip_direction: bool = False,
        direction_dimension_name: str = "",
        geometry_pattern: bool = True,
        equal_spacing: bool = True,
        vary_instance: bool = False,
    ) -> Any:
        """Create a circular pattern from the current ordered selection.

        SOLIDWORKS expects the rotation axis selected with mark 1 and seed
        features selected with mark 4 before this call.
        """
        feature = self.com.FeatureCircularPattern4(
            int(instances),
            float(angle),
            bool(flip_direction),
            str(direction_dimension_name),
            bool(geometry_pattern),
            bool(equal_spacing),
            bool(vary_instance),
        )
        if feature is None:
            raise SolidWorksError("Failed to create circular pattern from selected entities")
        return feature

    def loft_boss(
        self,
        *,
        closed: bool = False,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
        start_tangent_length: float = 0.0,
        end_tangent_length: float = 0.0,
        start_tangent_dir: bool = False,
        end_tangent_dir: bool = False,
        merge: bool = True,
        guide_curve_influence: int = 0,
    ) -> Any:
        feature = self.com.InsertProtrusionBlend2(
            bool(closed),
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
            float(start_tangent_length),
            float(end_tangent_length),
            bool(start_tangent_dir),
            bool(end_tangent_dir),
            False,
            0.0,
            0.0,
            0,
            bool(merge),
            True,
            True,
            int(guide_curve_influence),
        )
        if feature is None:
            raise SolidWorksError("Failed to create loft boss")
        return feature

    def loft_surface(
        self,
        *,
        closed: bool = False,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
    ) -> Any:
        result = self.model.com.InsertLoftRefSurface2(
            bool(closed),
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
        )
        if result is False:
            raise SolidWorksError("Failed to create loft surface")

    def loft_cut(
        self,
        *,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
        merge: bool = True,
    ) -> Any:
        """Cut the active body using the active loft profile selections.
        The caller must have already selected 2+ profile sketches
        (with mark=1 each) using :pymeth:`select_object` before
        calling this method. ``merge`` controls whether the cut
        removes the cut volume from the active body (``True``) or
        produces a separate removed volume.
        """
        feature = self.com.InsertCutBlend(
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError("Failed to create loft cut")
        return feature

    def thicken_selected(
        self, thickness: float, *, direction: int = 0, fill_volume: bool = False, merge: bool = True
    ) -> Any:
        feature = self.com.FeatureBossThicken(
            float(thickness), int(direction), 0, bool(fill_volume), bool(merge), True, True
        )
        if feature is None:
            raise SolidWorksError("Failed to thicken selected surface")
        return feature

    def fill_surface_selected(self, *, resolution: int = 3) -> Any:
        feature = self.com.InsertFillSurface(int(resolution))
        if feature is None:
            raise SolidWorksError("Failed to create fill surface from selected boundary")
        return feature

    def knit_selected(
        self,
        *,
        try_to_form_solid: bool = True,
        merge_entities: bool = True,
        knit_tolerance: float = 0.00001,
        use_gap_filters: bool = False,
        max_gap: float = 0.0001,
    ) -> Any:
        feature = self.com.InsertSewRefSurface(
            bool(use_gap_filters),
            bool(try_to_form_solid),
            bool(merge_entities),
            float(knit_tolerance),
            float(max_gap),
        )
        if feature is None:
            raise SolidWorksError("Failed to knit selected surfaces")
        return feature

    def offset_plane(self, distance: float, *, flip: bool = False) -> Any:
        constraint = RefPlaneConstraint.Distance | (RefPlaneConstraint.OptionFlip if flip else RefPlaneConstraint.NONE)
        plane = self.com.InsertRefPlane(int(constraint), float(distance), 0, 0.0, 0, 0.0)
        if plane is None:
            raise SolidWorksError("Failed to create offset reference plane")
        return plane


    def mirror_selected(self, *, merge: bool = True) -> Any:
        """Mirror the current selection across a pre-selected plane.

        The caller must have selected the mirror plane (mark=1) and
        the seed features (mark=4) before calling this method.
        """
        feature = self.com.FeatureMirror3(
            2,  # n_instances (original + mirror)
            None,  # mirror_plane -- pre-selected
            None,  # features -- pre-selected
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError('Failed to create mirror feature')
        return feature

    def linear_pattern_selected(
        self, count: int, spacing: float, *, merge: bool = True
    ) -> Any:
        """Create a linear pattern from the current selection.

        The caller must have selected the direction reference (mark=1)
        and the seed features (mark=4) before calling this method.
        """
        feature = self.com.FeatureLinearPattern3(
            int(count),
            float(spacing),
            None,  # direction -- pre-selected
            None,  # features -- pre-selected
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError('Failed to create linear pattern')
        return feature

    def shell_selected(self, thickness: float, *, remove_faces: bool = True) -> Any:
        """Shell the selected faces.

        The caller must have selected the faces to remove (mark=1)
        before calling this method.  If no faces are selected, the
        body is hollowed uniformly.
        """
        feature = self.com.InsertFeatureShell(
            float(thickness),
            bool(remove_faces),
        )
        if feature is None:
            raise SolidWorksError('Failed to create shell feature')
        return feature

    def draft_selected(
        self,
        angle: float,
        *,
        draft_type: int = 0,
    ) -> Any:
        """Create a draft on the selected faces.

        The caller must have selected the neutral plane (mark=1) and
        the faces to draft (mark=2) before calling this method.
        """
        feature = self.com.InsertFeatureDraft(
            int(draft_type),
            float(angle),
            None,  # direction -- pre-selected neutral plane
            None,  # faces -- pre-selected
        )
        if feature is None:
            raise SolidWorksError('Failed to create draft feature')
        return feature

    def call(self, name: str, *args: Any, require: bool = True) -> Any:
        result = getattr(self.com, name)(*args)
        if require and result is None:
            raise SolidWorksError(f"FeatureManager.{name} returned None")
        return result


class DrawingDoc(ModelDoc):
    """SOLIDWORKS Drawing document wrapper."""

    def insert_model_view(
        self,
        model_path: str | Path,
        *,
        view_type: str = 'front',
        x: float = 0.0,
        y: float = 0.0,
        scale: float = 1.0,
    ) -> Any:
        """Insert a model view into the drawing.

        Uses InsertModelInPrefPosition or CreateDrawView depending on
        the SOLIDWORKS version available.
        """
        path = str(Path(model_path).resolve())
        # Attempt CreateDrawView (newer API)
        try:
            view = self.com.CreateDrawView(
                path,  # model name
                float(x),  # X
                float(y),  # Y
                float(scale),  # scale
            )
            if view is not None:
                return view
        except (AttributeError, TypeError):
            pass
        # Fallback to InsertModelInPrefPosition
        try:
            view = self.com.InsertModelInPrefPosition(path)
            if view is not None:
                return view
        except (AttributeError, TypeError):
            pass
        raise SolidWorksError(f'Failed to insert model view: {path}')

    def add_dimension(
        self,
        entity_a: str,
        entity_b: str,
        value: float,
        *,
        dim_type: str = 'linear',
    ) -> Any:
        """Add a dimension between two entities.

        The caller must have selected the two entities before calling.
        """
        try:
            # Attempt to use the dimension API
            dim = self.com.CreateText2(
                f'{value:.3f}',
                float(0),  # X
                float(0),  # Y
                float(0),  # Z
                float(0),  # height
                int(0),    # angle
            )
            if dim is not None:
                return dim
        except (AttributeError, TypeError):
            pass
        return None

    def add_sheet(self, name: str = 'Sheet2') -> Any:
        """Add a new sheet to the drawing."""
        try:
            sheet = self.com.NewSheet3(
                str(name),  # name
                12,  # paper size (A4)
                1.0,  # scale1
                1.0,  # scale2
                True,  # first angle
                0,  # template
            )
            return sheet
        except (AttributeError, TypeError):
            pass
        return None

