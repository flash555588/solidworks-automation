"""Precision control and mesh settings for SOLIDWORKS models.

Inspired by text-to-cad's precision approach:
- Linear and angular deflection for mesh quality
- Configurable tolerance levels
- Geometry validation with precision control
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class MeshQuality(Enum):
    """Mesh quality presets."""

    DRAFT = auto()       # Fast, low quality
    LOW = auto()         # Low quality
    MEDIUM = auto()      # Medium quality
    HIGH = auto()        # High quality
    ULTRA = auto()       # Ultra high quality

    @property
    def linear_deflection(self) -> float:
        """Get linear deflection in meters."""
        settings = {
            MeshQuality.DRAFT: 0.01,
            MeshQuality.LOW: 0.005,
            MeshQuality.MEDIUM: 0.002,
            MeshQuality.HIGH: 0.001,
            MeshQuality.ULTRA: 0.0005,
        }
        return settings[self]

    @property
    def angular_deflection(self) -> float:
        """Get angular deflection in radians."""
        settings = {
            MeshQuality.DRAFT: 0.5,
            MeshQuality.LOW: 0.3,
            MeshQuality.MEDIUM: 0.2,
            MeshQuality.HIGH: 0.1,
            MeshQuality.ULTRA: 0.05,
        }
        return settings[self]

    @property
    def description(self) -> str:
        """Get human-readable description."""
        descriptions = {
            MeshQuality.DRAFT: "Draft (fast, low quality)",
            MeshQuality.LOW: "Low quality",
            MeshQuality.MEDIUM: "Medium quality",
            MeshQuality.HIGH: "High quality",
            MeshQuality.ULTRA: "Ultra high quality",
        }
        return descriptions[self]


@dataclass
class MeshSettings:
    """Mesh generation settings."""

    linear_deflection: float = 0.002    # meters
    angular_deflection: float = 0.2     # radians
    quality: MeshQuality = MeshQuality.MEDIUM

    @classmethod
    def from_quality(cls, quality: MeshQuality) -> MeshSettings:
        """Create settings from quality preset."""
        return cls(
            linear_deflection=quality.linear_deflection,
            angular_deflection=quality.angular_deflection,
            quality=quality,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "linearDeflection": self.linear_deflection,
            "angularDeflection": self.angular_deflection,
            "quality": self.quality.name,
        }


@dataclass
class PrecisionSettings:
    """Precision settings for geometry operations."""

    # Tolerance for comparisons
    length_tolerance: float = 0.0001    # 0.1mm
    angle_tolerance: float = 0.001      # ~0.06 degrees
    volume_tolerance: float = 0.001     # 0.1%

    # Mesh settings
    mesh: MeshSettings | None = None

    # Validation settings
    require_manifold: bool = True
    min_face_area: float = 1e-10        # m²
    min_edge_length: float = 1e-6       # m

    def __post_init__(self) -> None:
        if self.mesh is None:
            self.mesh = MeshSettings.from_quality(MeshQuality.MEDIUM)

    @classmethod
    def draft(cls) -> PrecisionSettings:
        """Draft precision (fast, low accuracy)."""
        return cls(
            length_tolerance=0.001,
            angle_tolerance=0.01,
            volume_tolerance=0.01,
            mesh=MeshSettings.from_quality(MeshQuality.DRAFT),
            require_manifold=False,
        )

    @classmethod
    def standard(cls) -> PrecisionSettings:
        """Standard precision."""
        return cls(
            length_tolerance=0.0001,
            angle_tolerance=0.001,
            volume_tolerance=0.001,
            mesh=MeshSettings.from_quality(MeshQuality.MEDIUM),
            require_manifold=True,
        )

    @classmethod
    def high(cls) -> PrecisionSettings:
        """High precision."""
        return cls(
            length_tolerance=0.00001,
            angle_tolerance=0.0001,
            volume_tolerance=0.0001,
            mesh=MeshSettings.from_quality(MeshQuality.HIGH),
            require_manifold=True,
        )

    @classmethod
    def ultra(cls) -> PrecisionSettings:
        """Ultra high precision."""
        return cls(
            length_tolerance=0.000001,
            angle_tolerance=0.00001,
            volume_tolerance=0.00001,
            mesh=MeshSettings.from_quality(MeshQuality.ULTRA),
            require_manifold=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lengthTolerance": self.length_tolerance,
            "angleTolerance": self.angle_tolerance,
            "volumeTolerance": self.volume_tolerance,
            "mesh": self.mesh.to_dict(),
            "requireManifold": self.require_manifold,
            "minFaceArea": self.min_face_area,
            "minEdgeLength": self.min_edge_length,
        }


class PrecisionValidator:
    """Validates geometry with precision control."""

    def __init__(self, settings: PrecisionSettings | None = None) -> None:
        self.settings = settings or PrecisionSettings.standard()

    def validate_length(
        self,
        actual: float,
        expected: float,
        *,
        name: str = "length",
    ) -> tuple[bool, str]:
        """Validate a length measurement."""
        diff = abs(actual - expected)
        if diff <= self.settings.length_tolerance:
            return True, ""
        return False, f"{name}: expected {expected:.6f}m, got {actual:.6f}m (diff={diff:.6f}m)"

    def validate_angle(
        self,
        actual: float,
        expected: float,
        *,
        name: str = "angle",
    ) -> tuple[bool, str]:
        """Validate an angle measurement."""
        diff = abs(actual - expected)
        if diff <= self.settings.angle_tolerance:
            return True, ""
        return False, f"{name}: expected {expected:.4f}rad, got {actual:.4f}rad (diff={diff:.4f}rad)"

    def validate_volume(
        self,
        actual: float,
        expected: float,
        *,
        name: str = "volume",
    ) -> tuple[bool, str]:
        """Validate volume with relative tolerance."""
        if expected == 0:
            return actual == 0, f"{name}: expected 0, got {actual}"
        relative_diff = abs(actual - expected) / abs(expected)
        if relative_diff <= self.settings.volume_tolerance:
            return True, ""
        return False, f"{name}: expected {expected:.6e}m³, got {actual:.6e}m³ (diff={relative_diff:.2%})"

    def validate_dimensions(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
        *,
        name: str = "dimensions",
    ) -> list[tuple[bool, str]]:
        """Validate 3D dimensions."""
        results = []
        for i, (a, e) in enumerate(zip(actual, expected)):
            axis = ['x', 'y', 'z'][i]
            passed, msg = self.validate_length(a, e, name=f"{name}.{axis}")
            results.append((passed, msg))
        return results

    def validate_bbox(
        self,
        actual_min: tuple[float, float, float],
        actual_max: tuple[float, float, float],
        expected_min: tuple[float, float, float],
        expected_max: tuple[float, float, float],
    ) -> list[tuple[bool, str]]:
        """Validate bounding box."""
        results = []
        for i, axis in enumerate(['x', 'y', 'z']):
            # Check min
            passed, msg = self.validate_length(
                actual_min[i], expected_min[i],
                name=f"bbox_min.{axis}",
            )
            results.append((passed, msg))
            # Check max
            passed, msg = self.validate_length(
                actual_max[i], expected_max[i],
                name=f"bbox_max.{axis}",
            )
            results.append((passed, msg))
        return results


def create_precision_validator(
    quality: MeshQuality = MeshQuality.MEDIUM,
) -> PrecisionValidator:
    """Create a precision validator with specified quality.

    Example::

        validator = create_precision_validator(MeshQuality.HIGH)

        # Validate dimensions
        passed, msg = validator.validate_length(
            actual=0.1001,
            expected=0.1,
            name="width",
        )
        if not passed:
            print(f"Validation failed: {msg}")
    """
    # Map quality to precision settings
    quality_settings = {
        MeshQuality.DRAFT: PrecisionSettings.draft(),
        MeshQuality.LOW: PrecisionSettings(
            length_tolerance=0.0005,
            angle_tolerance=0.005,
            volume_tolerance=0.005,
            mesh=MeshSettings.from_quality(MeshQuality.LOW),
        ),
        MeshQuality.MEDIUM: PrecisionSettings.standard(),
        MeshQuality.HIGH: PrecisionSettings.high(),
        MeshQuality.ULTRA: PrecisionSettings.ultra(),
    }
    settings = quality_settings.get(quality, PrecisionSettings.standard())
    return PrecisionValidator(settings)
