"""Enhanced geometry analysis and validation with high-precision features.

Inspired by text-to-cad's analysis.py and validators.py:
- Detailed geometry facts (bbox, center, axis alignment, volume, surface area)
- Validation assertions with tolerance
- Comprehensive validation reports
- Geometry quality checks
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .constants import BodyType

logger = logging.getLogger(__name__)


class PrecisionLevel(Enum):
    """Precision levels for validation."""

    COARSE = auto()      # 1mm tolerance
    STANDARD = auto()    # 0.1mm tolerance
    FINE = auto()        # 0.01mm tolerance
    HIGH = auto()        # 0.001mm tolerance
    ULTRA = auto()       # 0.0001mm tolerance

    @property
    def tolerance_meters(self) -> float:
        """Get tolerance in meters."""
        tolerances = {
            PrecisionLevel.COARSE: 0.001,
            PrecisionLevel.STANDARD: 0.0001,
            PrecisionLevel.FINE: 0.00001,
            PrecisionLevel.HIGH: 0.000001,
            PrecisionLevel.ULTRA: 0.0000001,
        }
        return tolerances[self]


@dataclass
class GeometryFacts:
    """Detailed geometry facts for a model."""

    # Bounding box
    bbox_min: tuple[float, float, float] | None = None
    bbox_max: tuple[float, float, float] | None = None

    # Derived measurements
    size: tuple[float, float, float] | None = None
    center: tuple[float, float, float] | None = None
    diagonal: float | None = None

    # Axis alignment
    extent_axis: str | None = None  # 'x', 'y', or 'z' - longest dimension
    is_axial: bool = False

    # Volume and surface area
    volume: float | None = None
    surface_area: float | None = None

    # Mass properties (if available)
    mass: float | None = None
    center_of_mass: tuple[float, float, float] | None = None
    moment_of_inertia: tuple[float, float, float] | None = None

    # Body information
    body_count: int = 0
    solid_count: int = 0
    surface_count: int = 0

    # Feature information
    feature_count: int = 0
    feature_errors: int = 0

    # Geometry quality
    is_manifold: bool | None = None
    has_degenerate_faces: bool | None = None
    min_face_area: float | None = None
    max_face_area: float | None = None

    # Projection geometry (v0.2) -- orthographic view areas
    # computed from the bounding-box 2-D projections.  These
    # are coarse approximations (they treat the bbox as the
    # silhouette); a future v0.3 can switch to real Drawing
    # view silhouette extraction via the SOLIDWORKS API.
    projection_area_front: float | None = None  # YZ plane
    projection_area_top: float | None = None    # XY plane
    projection_area_side: float | None = None   # XZ plane

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": {
                "min": list(self.bbox_min) if self.bbox_min else None,
                "max": list(self.bbox_max) if self.bbox_max else None,
            },
            "size": list(self.size) if self.size else None,
            "center": list(self.center) if self.center else None,
            "diagonal": self.diagonal,
            "extentAxis": self.extent_axis,
            "isAxial": self.is_axial,
            "volume": self.volume,
            "surfaceArea": self.surface_area,
            "mass": self.mass,
            "centerOfMass": list(self.center_of_mass) if self.center_of_mass else None,
            "momentOfInertia": list(self.moment_of_inertia) if self.moment_of_inertia else None,
            "bodyCount": self.body_count,
            "solidCount": self.solid_count,
            "surfaceCount": self.surface_count,
            "featureCount": self.feature_count,
            "featureErrors": self.feature_errors,
            "isManifold": self.is_manifold,
            "hasDegenerateFaces": self.has_degenerate_faces,
            "minFaceArea": self.min_face_area,
            "maxFaceArea": self.max_face_area,
            "projectionAreaFront": self.projection_area_front,
            "projectionAreaTop": self.projection_area_top,
            "projectionAreaSide": self.projection_area_side,
        }


@dataclass
class ValidationResult:
    """Result of a validation check."""

    check_name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    tolerance: float = 0.0
    message: str = ""
    severity: str = "error"  # "error", "warning", "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "tolerance": self.tolerance,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class ValidationReport:
    """Comprehensive validation report."""

    model_name: str = ""
    timestamp: str = ""
    precision_level: PrecisionLevel = PrecisionLevel.STANDARD

    # Geometry facts
    facts: GeometryFacts | None = None

    # Validation results
    results: list[ValidationResult] = field(default_factory=list)

    # Summary
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0

    @property
    def success(self) -> bool:
        return self.failed_checks == 0

    @property
    def has_warnings(self) -> bool:
        return self.warning_checks > 0

    def add_result(self, result: ValidationResult) -> None:
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        elif result.severity == "warning":
            self.warning_checks += 1
        else:
            self.failed_checks += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "timestamp": self.timestamp,
            "precisionLevel": self.precision_level.name,
            "facts": self.facts.to_dict() if self.facts else None,
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total": self.total_checks,
                "passed": self.passed_checks,
                "failed": self.failed_checks,
                "warnings": self.warning_checks,
                "success": self.success,
            },
        }

    def summary(self) -> str:
        lines = [f"Validation Report: {self.model_name}"]
        lines.append(f"  Precision: {self.precision_level.name}")

        if self.facts:
            f = self.facts
            if f.size:
                lines.append(f"  Size: {f.size[0]:.6f} x {f.size[1]:.6f} x {f.size[2]:.6f} m")
            if f.center:
                lines.append(f"  Center: ({f.center[0]:.6f}, {f.center[1]:.6f}, {f.center[2]:.6f})")
            if f.volume is not None:
                lines.append(f"  Volume: {f.volume:.6e} m³")
            if f.surface_area is not None:
                lines.append(f"  Surface Area: {f.surface_area:.6e} m²")
            lines.append(f"  Bodies: {f.body_count} (Solid: {f.solid_count}, Surface: {f.surface_count})")
            lines.append(f"  Features: {f.feature_count} ({f.feature_errors} errors)")

        lines.append(f"  Checks: {self.passed_checks}/{self.total_checks} passed")
        if self.failed_checks > 0:
            lines.append(f"  Failed: {self.failed_checks}")
        if self.warning_checks > 0:
            lines.append(f"  Warnings: {self.warning_checks}")

        failed = [r for r in self.results if not r.passed]
        if failed:
            lines.append("\nFailed checks:")
            for r in failed:
                lines.append(f"  [{r.severity.upper()}] {r.check_name}: {r.message}")

        return "\n".join(lines)


class GeometryAnalyzer:
    """Analyzes model geometry and extracts facts."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def extract_facts(self) -> GeometryFacts:
        """Extract comprehensive geometry facts."""
        facts = GeometryFacts()

        # Get bounding box
        bbox = self._get_bounding_box()
        if bbox:
            facts.bbox_min = bbox[0]
            facts.bbox_max = bbox[1]
            facts.size = self._compute_size(bbox)
            facts.center = self._compute_center(bbox)
            facts.diagonal = self._compute_diagonal(facts.size)
            facts.extent_axis = self._compute_extent_axis(facts.size)
            facts.is_axial = self._check_axial_alignment(facts.size)
            # v0.2: orthographic projection areas from bbox.
            # front = YZ, top = XY, side = XZ.
            sx, sy, sz = facts.size
            facts.projection_area_front = float(sy * sz)
            facts.projection_area_top = float(sx * sy)
            facts.projection_area_side = float(sx * sz)

        # Get body count
        facts.body_count = self._get_body_count()
        facts.solid_count = self._get_solid_count()
        facts.surface_count = self._get_surface_count()

        # Get volume and surface area
        facts.volume = self._get_volume()
        facts.surface_area = self._get_surface_area()

        # Get mass properties
        mass_props = self._get_mass_properties()
        if mass_props:
            facts.mass = mass_props.get("mass")
            facts.center_of_mass = mass_props.get("center_of_mass")
            facts.moment_of_inertia = mass_props.get("moment_of_inertia")

        # Get feature info
        facts.feature_count = self._get_feature_count()
        facts.feature_errors = self._get_feature_error_count()

        return facts

    def _get_bounding_box(self) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        try:
            box = self.model.com.Extension.GetBox()
            if box and len(box) >= 6:
                return (
                    (float(box[0]), float(box[1]), float(box[2])),
                    (float(box[3]), float(box[4]), float(box[5])),
                )
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get bounding box: %s", e)
        return None

    def _compute_size(self, bbox: tuple[tuple, tuple]) -> tuple[float, float, float]:
        min_pt, max_pt = bbox
        return (
            max_pt[0] - min_pt[0],
            max_pt[1] - min_pt[1],
            max_pt[2] - min_pt[2],
        )

    def _compute_center(self, bbox: tuple[tuple, tuple]) -> tuple[float, float, float]:
        min_pt, max_pt = bbox
        return (
            (min_pt[0] + max_pt[0]) / 2.0,
            (min_pt[1] + max_pt[1]) / 2.0,
            (min_pt[2] + max_pt[2]) / 2.0,
        )

    def _compute_diagonal(self, size: tuple[float, float, float] | None) -> float | None:
        if size is None:
            return None
        return math.sqrt(sum(s * s for s in size))

    def _compute_extent_axis(self, size: tuple[float, float, float] | None) -> str | None:
        if size is None:
            return None
        axes = ['x', 'y', 'z']
        max_idx = max(range(3), key=lambda i: size[i])
        return axes[max_idx]

    def _check_axial_alignment(self, size: tuple[float, float, float] | None, threshold: float = 0.95) -> bool:
        if size is None:
            return False
        total = sum(size)
        if total <= 0:
            return False
        max_size = max(size)
        return (max_size / total) >= threshold

    def _get_body_count(self) -> int:
        try:
            bodies = self.model.bodies()
            return len(bodies) if bodies else 0
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get body count: %s", e)
            return 0

    def _get_solid_count(self) -> int:
        try:
            bodies = self.model.bodies()
            if not bodies:
                return 0
            count = 0
            for body in bodies:
                body_type = getattr(body, "GetType", lambda: -1)()
                if body_type == BodyType.Solid:
                    count += 1
            return count
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get solid count: %s", e)
            return 0

    def _get_surface_count(self) -> int:
        try:
            bodies = self.model.bodies()
            if not bodies:
                return 0
            count = 0
            for body in bodies:
                body_type = getattr(body, "GetType", lambda: -1)()
                if body_type == BodyType.Sheet:
                    count += 1
            return count
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get surface count: %s", e)
            return 0

    def _get_volume(self) -> float | None:
        try:
            bodies = self.model.bodies()
            if not bodies:
                return None
            total_volume = 0.0
            for body in bodies:
                props = body.GetMassProperties(0)
                if props and len(props) >= 4:
                    total_volume += float(props[3])
            return total_volume if total_volume > 0 else None
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get volume: %s", e)
            return None

    def _get_surface_area(self) -> float | None:
        try:
            bodies = self.model.bodies()
            if not bodies:
                return None
            total_area = 0.0
            for body in bodies:
                props = body.GetMassProperties(0)
                if props and len(props) >= 5:
                    total_area += float(props[4])
            return total_area if total_area > 0 else None
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get surface area: %s", e)
            return None

    def _get_mass_properties(self) -> dict[str, Any] | None:
        try:
            bodies = self.model.bodies()
            if not bodies:
                return None

            total_mass = 0.0
            total_volume = 0.0
            com_x, com_y, com_z = 0.0, 0.0, 0.0

            for body in bodies:
                props = body.GetMassProperties(0)
                if props and len(props) >= 7:
                    mass = float(props[3])  # Volume as mass proxy
                    total_mass += mass
                    total_volume += float(props[3])
                    com_x += float(props[0]) * mass
                    com_y += float(props[1]) * mass
                    com_z += float(props[2]) * mass

            if total_mass > 0:
                return {
                    "mass": total_mass,
                    "center_of_mass": (com_x / total_mass, com_y / total_mass, com_z / total_mass),
                    "moment_of_inertia": None,  # Would need separate API call
                }
            return None
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get mass properties: %s", e)
            return None

    def _get_feature_count(self) -> int:
        try:
            features = list(self.model.iter_features())
            return len(features)
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get feature count: %s", e)
            return 0

    def _get_feature_error_count(self) -> int:
        try:
            errors = self.model.feature_errors()
            return len(errors) if errors else 0
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get feature error count: %s", e)
            return 0


class GeometryValidator:
    """Validates geometry against expected values."""

    def __init__(self, analyzer: GeometryAnalyzer) -> None:
        self.analyzer = analyzer

    def validate(
        self,
        *,
        expected_size: tuple[float, float, float] | None = None,
        expected_center: tuple[float, float, float] | None = None,
        expected_volume: float | None = None,
        size_tolerance: float | None = None,
        center_tolerance: float | None = None,
        volume_tolerance: float | None = None,
        precision: PrecisionLevel = PrecisionLevel.STANDARD,
        min_body_count: int = 1,
        max_body_count: int | None = None,
        require_single_solid: bool = False,
        require_manifold: bool = False,
    ) -> ValidationReport:
        """Run comprehensive validation."""
        report = ValidationReport(precision_level=precision)
        report.facts = self.analyzer.extract_facts()
        facts = report.facts

        # Use precision level for default tolerances
        if size_tolerance is None:
            size_tolerance = precision.tolerance_meters
        if center_tolerance is None:
            center_tolerance = precision.tolerance_meters
        if volume_tolerance is None:
            volume_tolerance = precision.tolerance_meters * 100  # Volume has larger tolerance

        # Check size
        if expected_size and facts.size:
            for i, (axis, expected) in enumerate(zip(['x', 'y', 'z'], expected_size)):
                actual = facts.size[i]
                passed = abs(actual - expected) <= size_tolerance
                report.add_result(ValidationResult(
                    check_name=f"size_{axis}",
                    passed=passed,
                    expected=expected,
                    actual=actual,
                    tolerance=size_tolerance,
                    message=f"{axis} size: expected {expected:.6f}, got {actual:.6f}" if not passed else "",
                ))

        # Check center
        if expected_center and facts.center:
            for i, (axis, expected) in enumerate(zip(['x', 'y', 'z'], expected_center)):
                actual = facts.center[i]
                passed = abs(actual - expected) <= center_tolerance
                report.add_result(ValidationResult(
                    check_name=f"center_{axis}",
                    passed=passed,
                    expected=expected,
                    actual=actual,
                    tolerance=center_tolerance,
                    message=f"{axis} center: expected {expected:.6f}, got {actual:.6f}" if not passed else "",
                ))

        # Check volume
        if expected_volume and facts.volume:
            passed = abs(facts.volume - expected_volume) <= volume_tolerance
            report.add_result(ValidationResult(
                check_name="volume",
                passed=passed,
                expected=expected_volume,
                actual=facts.volume,
                tolerance=volume_tolerance,
                message=f"Volume: expected {expected_volume:.6e}, got {facts.volume:.6e}" if not passed else "",
            ))

        # Check body count
        if min_body_count is not None:
            passed = facts.body_count >= min_body_count
            report.add_result(ValidationResult(
                check_name="min_body_count",
                passed=passed,
                expected=min_body_count,
                actual=facts.body_count,
                message=f"Body count: expected >= {min_body_count}, got {facts.body_count}" if not passed else "",
            ))

        if max_body_count is not None:
            passed = facts.body_count <= max_body_count
            report.add_result(ValidationResult(
                check_name="max_body_count",
                passed=passed,
                expected=max_body_count,
                actual=facts.body_count,
                message=f"Body count: expected <= {max_body_count}, got {facts.body_count}" if not passed else "",
            ))

        # Check single solid
        if require_single_solid:
            passed = facts.solid_count == 1
            report.add_result(ValidationResult(
                check_name="single_solid",
                passed=passed,
                expected=1,
                actual=facts.solid_count,
                message=f"Solid count: expected 1, got {facts.solid_count}" if not passed else "",
            ))

        # Check feature errors
        if facts.feature_errors > 0:
            report.add_result(ValidationResult(
                check_name="feature_errors",
                passed=False,
                expected=0,
                actual=facts.feature_errors,
                message=f"Feature errors: {facts.feature_errors}",
                severity="warning",
            ))

        return report


def analyze_model(model: Any) -> GeometryFacts:
    """Convenience function to extract geometry facts."""
    analyzer = GeometryAnalyzer(model)
    return analyzer.extract_facts()


def validate_model(
    model: Any,
    *,
    expected_size: tuple[float, float, float] | None = None,
    expected_center: tuple[float, float, float] | None = None,
    expected_volume: float | None = None,
    precision: PrecisionLevel = PrecisionLevel.STANDARD,
    min_body_count: int = 1,
    max_body_count: int | None = None,
    require_single_solid: bool = False,
) -> ValidationReport:
    """Convenience function to validate model geometry."""
    analyzer = GeometryAnalyzer(model)
    validator = GeometryValidator(analyzer)
    return validator.validate(
        expected_size=expected_size,
        expected_center=expected_center,
        expected_volume=expected_volume,
        precision=precision,
        min_body_count=min_body_count,
        max_body_count=max_body_count,
        require_single_solid=require_single_solid,
    )
