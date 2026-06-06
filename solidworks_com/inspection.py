"""Geometry inspection and validation for SOLIDWORKS models.

Inspired by text-to-cad's inspection principles:
- Use programmatic geometry checks as validation source of truth
- Validate bounding box, features, and dimensions
- Report only checks that actually ran
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """3D bounding box."""

    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def depth(self) -> float:
        return self.z_max - self.z_min

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.x_min + self.x_max) / 2,
            (self.y_min + self.y_max) / 2,
            (self.z_min + self.z_max) / 2,
        )

    @property
    def volume(self) -> float:
        return self.width * self.height * self.depth

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a point is inside the bounding box."""
        return (
            self.x_min <= x <= self.x_max
            and self.y_min <= y <= self.y_max
            and self.z_min <= z <= self.z_max
        )

    def overlaps(self, other: BoundingBox) -> bool:
        """Check if this bounding box overlaps with another."""
        return (
            self.x_min <= other.x_max
            and self.x_max >= other.x_min
            and self.y_min <= other.y_max
            and self.y_max >= other.y_min
            and self.z_min <= other.z_max
            and self.z_max >= other.z_min
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "z_min": self.z_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "z_max": self.z_max,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
        }


@dataclass
class FeatureInfo:
    """Information about a model feature."""

    name: str
    type_name: str
    error_code: int = 0

    @property
    def has_error(self) -> bool:
        return self.error_code != 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "error_code": self.error_code,
            "has_error": self.has_error,
        }


@dataclass
class InspectionReport:
    """Report from geometry inspection."""

    bounding_box: BoundingBox | None = None
    features: list[FeatureInfo] | None = None
    body_count: int = 0
    validation_issues: list[str] | None = None

    @property
    def has_errors(self) -> bool:
        if self.validation_issues:
            return True
        if self.features:
            return any(f.has_error for f in self.features)
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "bounding_box": self.bounding_box.to_dict() if self.bounding_box else None,
            "features": [f.to_dict() for f in self.features] if self.features else None,
            "body_count": self.body_count,
            "validation_issues": self.validation_issues,
            "has_errors": self.has_errors,
        }

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = ["Inspection Report:"]

        if self.bounding_box:
            bb = self.bounding_box
            lines.append(f"  Bounding Box: {bb.width:.2f} x {bb.height:.2f} x {bb.depth:.2f} m")
            lines.append(f"  Center: ({bb.center[0]:.3f}, {bb.center[1]:.3f}, {bb.center[2]:.3f})")

        lines.append(f"  Bodies: {self.body_count}")

        if self.features:
            errors = [f for f in self.features if f.has_error]
            lines.append(f"  Features: {len(self.features)} total, {len(errors)} with errors")
            if errors:
                for f in errors:
                    lines.append(f"    - {f.name}: error code {f.error_code}")

        if self.validation_issues:
            lines.append(f"  Validation Issues: {len(self.validation_issues)}")
            for issue in self.validation_issues:
                lines.append(f"    - {issue}")

        return "\n".join(lines)


class ModelInspector:
    """Inspects and validates SOLIDWORKS model geometry."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def get_bounding_box(self) -> BoundingBox | None:
        """Get the model's bounding box."""
        try:
            box = self.model.com.Extension.GetBox()
            if box and len(box) >= 6:
                return BoundingBox(
                    x_min=float(box[0]),
                    y_min=float(box[1]),
                    z_min=float(box[2]),
                    x_max=float(box[3]),
                    y_max=float(box[4]),
                    z_max=float(box[5]),
                )
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to get bounding box: %s", e)
        return None

    def get_features(self) -> list[FeatureInfo]:
        """Get all features with their status."""
        features = []
        try:
            for feature in self.model.iter_features():
                name = self.model.feature_name(feature)
                type_name = self.model.feature_type(feature)
                error_code = self.model.feature_error_code(feature)
                features.append(FeatureInfo(
                    name=name,
                    type_name=type_name,
                    error_code=error_code,
                ))
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to enumerate features: %s", e)
        return features

    def get_body_count(self) -> int:
        """Get the number of bodies in the model."""
        try:
            bodies = self.model.bodies()
            return len(bodies) if bodies else 0
        except (AttributeError, TypeError) as e:
            logger.debug("get_body_count failed: %s", e)
            return 0

    def validate_dimensions(
        self,
        *,
        expected_width: float | None = None,
        expected_height: float | None = None,
        expected_depth: float | None = None,
        tolerance: float = 0.001,
    ) -> list[str]:
        """Validate model dimensions against expected values."""
        issues = []
        bb = self.get_bounding_box()
        if not bb:
            issues.append("Could not determine bounding box")
            return issues

        if expected_width is not None and abs(bb.width - expected_width) > tolerance:
            issues.append(
                f"Width mismatch: expected {expected_width:.3f}, got {bb.width:.3f}"
            )

        if expected_height is not None and abs(bb.height - expected_height) > tolerance:
            issues.append(
                f"Height mismatch: expected {expected_height:.3f}, got {bb.height:.3f}"
            )

        if expected_depth is not None and abs(bb.depth - expected_depth) > tolerance:
            issues.append(
                f"Depth mismatch: expected {expected_depth:.3f}, got {bb.depth:.3f}"
            )

        return issues

    def validate_features(self) -> list[str]:
        """Validate all features have no errors."""
        issues = []
        for feature in self.get_features():
            if feature.has_error:
                issues.append(f"Feature '{feature.name}' has error code {feature.error_code}")
        return issues

    def inspect(self) -> InspectionReport:
        """Perform a full inspection of the model."""
        report = InspectionReport()
        report.bounding_box = self.get_bounding_box()
        report.features = self.get_features()
        report.body_count = self.get_body_count()
        report.validation_issues = self.validate_features()
        return report

    def validate_model(
        self,
        *,
        expected_width: float | None = None,
        expected_height: float | None = None,
        expected_depth: float | None = None,
        require_single_body: bool = True,
    ) -> InspectionReport:
        """Validate model with specific checks."""
        report = self.inspect()

        # Check body count
        if require_single_body and report.body_count > 1:
            if report.validation_issues is None:
                report.validation_issues = []
            report.validation_issues.append(
                f"Expected single body, found {report.body_count}"
            )

        # Check dimensions
        dimension_issues = self.validate_dimensions(
            expected_width=expected_width,
            expected_height=expected_height,
            expected_depth=expected_depth,
        )
        if report.validation_issues is None:
            report.validation_issues = []
        report.validation_issues.extend(dimension_issues)

        return report
