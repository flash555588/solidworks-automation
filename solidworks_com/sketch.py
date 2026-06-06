from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from .com import (
    call_member,
    call_or_value,
    double_array,
    empty_variant,
    import_pywin32,
    member_value,
    variant_array,
    variant_byref,
)
from .constants import ConstraintType
from .errors import SolidWorksError
from .geometry import Point, flatten_points

logger = logging.getLogger(__name__)

FeaturePredicate = Callable[[Any], bool]
SegmentPredicate = Callable[["SketchSegment"], bool]
ContourPredicate = Callable[["SketchContour"], bool]


@dataclass(frozen=True)
class SketchSegment:
    model: Any
    com: Any

    @property
    def type(self) -> int | None:
        try:
            return int(member_value(self.com, "GetType"))
        except (AttributeError, TypeError) as e:
            logger.debug("type failed: %s", e)
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
            except (AttributeError, TypeError) as e:
                logger.debug("curve_params failed for %s: %s", name, e)
                value = None
            if value is not None:
                return [float(item) for item in list(value)]
        return []


class SketchBuilder:
    def __init__(self, model: Any) -> None:
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

    def oblong(self, cx: float, cy: float, length: float, width: float, *, z: float = 0.0) -> Any:
        """Rectangular slot with semicircular ends (stadium / oblong shape).

        Produces a **guaranteed-closed** contour — use this instead of
        manual ``line`` + ``arc`` combinations, which require explicit
        Coincident constraints to be recognised as closed by SOLIDWORKS.

        Args:
            cx, cy: Slot centre in sketch coordinates (metres).
            length: Total length tip-to-tip (metres).
            width:  Slot width = diameter of the semicircular ends (metres).
            z:      In-plane Z (leave at 0.0 for normal sketch use).

        Raises:
            SolidWorksError: If ``ISketchManager.CreateOblong`` is absent
                (SOLIDWORKS < 2007). Fall back to ``corner_rectangle`` for
                simple rectangular slots in that case.
        """
        create_oblong = getattr(self.com, "CreateOblong", None)
        if not callable(create_oblong):
            raise SolidWorksError(
                "ISketchManager.CreateOblong not available on this SOLIDWORKS version; "
                "use corner_rectangle for simple rectangular slots"
            )
        half_len = length / 2.0
        half_w = width / 2.0
        return create_oblong(cx, cy, z, cx + half_len, cy + half_w, z)

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
    def __init__(self, model: Any, feature: Any) -> None:
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
    def __init__(self, model: Any, com: Any) -> None:
        self.model = model
        self.com = com

    @staticmethod
    def from_sketch(model: Any, sketch: Any) -> list[SketchContour]:
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
        except (AttributeError, TypeError) as e:
            logger.debug("sketch_segment_endpoint failed: %s", e)
    get_points = getattr(segment, "GetPoints2", None)
    if get_points is not None:
        try:
            points = _as_list(call_or_value(get_points))
            if points:
                return points[0] if start else points[-1]
        except (AttributeError, TypeError) as e:
            logger.debug("sketch_segment_endpoint failed: %s", e)
    raise SolidWorksError(f"Sketch segment does not expose {'start' if start else 'end'} point")


def _specific_sketch_segment(segment: Any) -> Any:
    _, win32com_client = import_pywin32()
    for interface_name in ("SketchLine", "SketchArc", "SketchSpline"):
        try:
            return win32com_client.CastTo(segment, interface_name)
        except (AttributeError, TypeError) as e:
            logger.debug("CastTo %s failed: %s", interface_name, e)
            continue
    return segment
