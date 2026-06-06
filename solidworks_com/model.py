from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .com import (
    call_member,
    call_or_value,
    empty_dispatch,
    empty_variant,
    int_byref,
    member_value,
    unpack_out_call,
)
from .constants import (
    MoveRollbackBarTo,
    SaveAsOptions,
    SaveAsVersion,
    SelectType,
)
from .errors import SolidWorksError
from .features import FeatureTools
from .geometry import Point
from .sketch import SketchBuilder, SketchContour, SketchEditor, SketchSegment, _as_list

logger = logging.getLogger(__name__)

FeaturePredicate = Callable[[Any], bool]
SegmentPredicate = Callable[["SketchSegment"], bool]
ContourPredicate = Callable[["SketchContour"], bool]


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
        except (AttributeError, TypeError) as e:
            logger.debug("ModelDoc.__repr__ failed: %s", e)
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
        except (AttributeError, TypeError) as e:
            logger.debug("feature_error_code failed: %s", e)
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

    def safe_size(self) -> tuple[float, float, float] | None:
        """Return (dx, dy, dz) model size in metres without raising.

        Tries ``Extension.GetBox()`` first (works for parts and assemblies),
        then falls back to ``GetPartBox``.  Returns ``None`` if both fail
        so callers can substitute a default value.
        """
        try:
            box = self.com.Extension.GetBox()
            if box and len(box) >= 6:
                return (
                    float(box[3]) - float(box[0]),
                    float(box[4]) - float(box[1]),
                    float(box[5]) - float(box[2]),
                )
        except Exception as e:
            logger.debug("Extension.GetBox() failed: %s", e)
        try:
            xmin, ymin, zmin, xmax, ymax, zmax = self.part_box(exact=True)
            return xmax - xmin, ymax - ymin, zmax - zmin
        except Exception as e:
            logger.debug("GetPartBox fallback failed: %s", e)
        return None

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
        if radius < 0:
            raise ValueError(f"extrude_cylinder radius must be non-negative, got {radius}")
        if depth < 0:
            raise ValueError(f"extrude_cylinder depth must be non-negative, got {depth}")
        self.clear_selection()
        cx, cy, cz = _face_centroid(face)
        with self.sketch_on_face_at(cx, cy, cz) as sk:
            sk.circle(float(center[0]), float(center[1]), float(radius))
        feature = self.features.extrude_blind(
            float(depth), merge=False, reverse=bool(reverse)
        )
        if feature is None:
            raise SolidWorksError(
                "Failed to extrude cylinder (FeatureExtrusion3 returned None)"
            )
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
        # SOLIDWORKS: select target body (mark=1), then select tool body (mark=2),
        # then call InsertCutFeature on the tool body.
        self.clear_selection()
        self.select_object(target_body, mark=1)
        self.select_object(tool_body, append=True, mark=2)
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
        if radius < 0:
            raise ValueError(f"make_hole radius must be non-negative, got {radius}")
        if depth < 0:
            raise ValueError(f"make_hole depth must be non-negative, got {depth}")
        cutter = self.extrude_cylinder(
            face, center=center, radius=radius, depth=depth, reverse=reverse
        )
        return self.bool_subtract(target_body, cutter, keep_tool=False)

    def bodies(self) -> list[Any]:
        """Return all bodies in the active part as a list."""
        result: list[Any] = []
        try:
            result = _as_list(call_or_value(lambda: self.com.GetBodies(0)))
        except Exception as e:
            logger.debug("bodies() failed: %s", e)
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
        except Exception as e:
            logger.debug("Feature replacement failed, rolling back: %s", e)
            # Transaction safety net: ensure rollback on any failure
            # before re-raising the original exception.
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
        """Get a ModelInspector for geometry inspection and validation."""
        from .inspection import ModelInspector

        return ModelInspector(self)

    @property
    def parameters(self) -> Any:
        """Get or create a ParameterManager for this model."""
        if not hasattr(self, '_parameters'):
            from .parameters import ParameterManager
            self._parameters = ParameterManager()
        return self._parameters

    @property
    def analyzer(self) -> Any:
        """Get a GeometryAnalyzer for extracting geometry facts."""
        from .analysis import GeometryAnalyzer

        return GeometryAnalyzer(self)

    @property
    def metadata_manager(self) -> Any:
        """Get a MetadataManager for tracking generation metadata."""
        if not hasattr(self, '_metadata_manager'):
            from .metadata import MetadataManager
            self._metadata_manager = MetadataManager(self)
        return self._metadata_manager

    @property
    def export_manager(self) -> Any:
        """Get an ExportManager for multi-format export."""
        if not hasattr(self, '_export_manager'):
            from .export import ExportManager
            self._export_manager = ExportManager(self)
        return self._export_manager


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
    except (AttributeError, TypeError) as e:
        logger.debug("_same_com_object failed: %s", e)
        return False
