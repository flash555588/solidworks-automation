"""Design rules and pre-flight validation for SOLIDWORKS automation.

This module encodes SOLIDWORKS modeling best practices as enforceable rules.
Calling these validators *before* submitting geometry to SOLIDWORKS catches
failures that would otherwise surface only as cryptic COM errors deep inside
the feature tree.

Failure modes addressed
-----------------------
- Revolve profiles with a closing line along the axis (most common failure)
- Revolve profiles that cross or have negative X coordinates
- Zero-length sketch segments that prevent sketch solve
- Disconnected / open profiles submitted to boss operations
- Feature depths that are zero, negative, or exceed model bounds
- Wall thickness below process minimums
- Hole diameters below tool / process minimums
- Fillet radii that exceed the adjacent edge length

Usage::

    from solidworks_com.design_rules import (
        DesignChecker, DesignProfile, validate_revolve_profile,
    )

    # Standalone revolve profile check (no model needed)
    from solidworks_com import mm
    lines = [
        (mm(0), mm(0), mm(13), mm(0)),
        (mm(13), mm(0), mm(13), mm(15)),
        (mm(13), mm(15), mm(0), mm(15)),   # ← axis-closing line! will be caught
    ]
    violations = validate_revolve_profile(lines, feature_name="Outer shell")
    for v in violations:
        print(v)

    # Full design checker with process profile
    checker = DesignChecker(profile=DesignProfile.FDM_PRINTING)
    checker.check_revolve_profile(lines, feature_name="Outer shell")
    checker.check_wall_thickness(mm(0.8), feature_name="Side wall")
    checker.check_hole(mm(1.5), feature_name="Mounting hole")
    print(checker.report())
    if checker.has_errors():
        raise RuntimeError("Design validation failed — fix errors before building")
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity / violation
# ---------------------------------------------------------------------------

class RuleSeverity(Enum):
    ERROR = auto()    # Will definitely fail or produce invalid geometry
    WARNING = auto()  # May fail or produce poor quality geometry
    INFO = auto()     # Best-practice suggestion only


@dataclass
class RuleViolation:
    """A single rule violation."""

    rule_name: str
    severity: RuleSeverity
    message: str
    feature: str = ""
    suggested_fix: str = ""

    def __str__(self) -> str:
        icons = {RuleSeverity.ERROR: "[ERROR]", RuleSeverity.WARNING: "[WARN]", RuleSeverity.INFO: "[INFO]"}
        prefix = icons[self.severity]
        feature_str = f" <{self.feature}>" if self.feature else ""
        fix_str = f"\n    Fix: {self.suggested_fix}" if self.suggested_fix else ""
        return f"{prefix}{feature_str} {self.message}{fix_str}"


# ---------------------------------------------------------------------------
# Design profiles — process-specific thresholds (all in metres)
# ---------------------------------------------------------------------------

class DesignProfile(Enum):
    """Manufacturing process profiles."""
    GENERAL          = "general"
    MACHINING        = "machining"
    INJECTION_MOLDING = "injection_molding"
    SHEET_METAL      = "sheet_metal"
    FDM_PRINTING     = "fdm_printing"


_THRESHOLDS: dict[DesignProfile, dict[str, Any]] = {
    DesignProfile.GENERAL: {
        "min_wall_m":          0.5e-3,
        "min_hole_m":          1.0e-3,
        "min_fillet_m":        0.1e-3,
        "max_aspect_ratio":    50.0,
        "require_draft":       False,
        "min_draft_deg":       0.0,
        "description":         "General / concept modelling",
    },
    DesignProfile.MACHINING: {
        "min_wall_m":          0.8e-3,
        "min_hole_m":          3.0e-3,   # smallest common end-mill
        "min_fillet_m":        0.5e-3,
        "max_aspect_ratio":    10.0,     # thin ribs difficult to machine
        "require_draft":       False,
        "min_draft_deg":       0.0,
        "description":         "CNC milling / turning",
    },
    DesignProfile.INJECTION_MOLDING: {
        "min_wall_m":          1.0e-3,
        "min_hole_m":          1.5e-3,
        "min_fillet_m":        0.5e-3,
        "max_aspect_ratio":    20.0,
        "require_draft":       True,
        "min_draft_deg":       1.0,
        "description":         "Injection moulding",
    },
    DesignProfile.SHEET_METAL: {
        "min_wall_m":          0.4e-3,
        "min_hole_m":          0.8e-3,
        "min_fillet_m":        0.1e-3,
        "max_aspect_ratio":    200.0,
        "require_draft":       False,
        "min_draft_deg":       0.0,
        "description":         "Sheet metal (laser / press brake)",
    },
    DesignProfile.FDM_PRINTING: {
        "min_wall_m":          1.5e-3,   # ~2 perimeters at 0.6 mm width
        "min_hole_m":          2.0e-3,
        "min_fillet_m":        0.4e-3,
        "max_aspect_ratio":    15.0,
        "require_draft":       False,
        "min_draft_deg":       0.0,
        "description":         "FDM / FFF 3D printing",
    },
}


# ---------------------------------------------------------------------------
# Standalone validators (no model required)
# ---------------------------------------------------------------------------

def validate_revolve_profile(
    lines: list[tuple[float, float, float, float]],
    *,
    tolerance: float = 1e-9,
    feature_name: str = "",
) -> list[RuleViolation]:
    """Validate revolve profile lines before submitting to SOLIDWORKS.

    The most common revolve failure is a closing line along the revolve axis
    (X = 0 for a Y-axis revolve).  SOLIDWORKS cannot distinguish the axis from
    the profile boundary and silently fails to create a solid body.

    Rules checked
    -------------
    - REVOLVE_NO_AXIS_LINE: no segment may have both endpoints at X ≈ 0
    - REVOLVE_PROFILE_CROSSES_AXIS: no X < 0 (profile must stay on one side)
    - SKETCH_ZERO_LENGTH_SEGMENT: no degenerate (zero-length) lines
    - SKETCH_DISCONNECTED_PROFILE: each line end should connect to the next start

    Args:
        lines: List of (x1, y1, x2, y2) line segments.
        tolerance: Distance tolerance for "on-axis" detection.
        feature_name: Feature name used in violation messages.

    Returns:
        List of :class:`RuleViolation`.  Empty list means valid.
    """
    violations: list[RuleViolation] = []

    for i, seg in enumerate(lines):
        x1, y1, x2, y2 = seg
        n = i + 1  # 1-based label

        # Axis-coincident line
        if abs(x1) <= tolerance and abs(x2) <= tolerance:
            violations.append(RuleViolation(
                rule_name="REVOLVE_NO_AXIS_LINE",
                severity=RuleSeverity.ERROR,
                message=(
                    f"Segment {n} lies entirely on the revolve axis (X=0): "
                    f"({x1:.6f}, {y1:.6f}) → ({x2:.6f}, {y2:.6f}).  "
                    "SOLIDWORKS cannot create a solid body when the profile "
                    "includes an edge coincident with the axis."
                ),
                feature=feature_name,
                suggested_fix=(
                    "Remove this segment.  Let the profile start and end on "
                    "the axis (X=0) at its two endpoints; do NOT draw a line "
                    "connecting them along the axis."
                ),
            ))

        # Profile crosses axis
        if x1 < -tolerance or x2 < -tolerance:
            violations.append(RuleViolation(
                rule_name="REVOLVE_PROFILE_CROSSES_AXIS",
                severity=RuleSeverity.ERROR,
                message=(
                    f"Segment {n} has X < 0: ({x1:.6f}, {y1:.6f}) → ({x2:.6f}, {y2:.6f}).  "
                    "The revolve profile must stay entirely on X ≥ 0."
                ),
                feature=feature_name,
                suggested_fix="Mirror the profile so all X values are non-negative.",
            ))

        # Zero-length segment
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= tolerance:
            violations.append(RuleViolation(
                rule_name="SKETCH_ZERO_LENGTH_SEGMENT",
                severity=RuleSeverity.ERROR,
                message=(
                    f"Segment {n} has zero length at ({x1:.6f}, {y1:.6f}).  "
                    "Zero-length segments prevent sketch solve."
                ),
                feature=feature_name,
                suggested_fix="Remove duplicate or coincident points.",
            ))

    # Connectivity check (each end should meet the next start)
    for i in range(len(lines) - 1):
        _, _, x2, y2 = lines[i]
        x1n, y1n, _, _ = lines[i + 1]
        gap = math.hypot(x2 - x1n, y2 - y1n)
        if gap > 1e-6:  # 1 µm tolerance
            violations.append(RuleViolation(
                rule_name="SKETCH_DISCONNECTED_PROFILE",
                severity=RuleSeverity.WARNING,
                message=(
                    f"Gap of {gap * 1000:.3f} mm between segment {i+1} end and "
                    f"segment {i+2} start.  A disconnected profile may not revolve correctly."
                ),
                feature=feature_name,
                suggested_fix=(
                    "Ensure each segment endpoint exactly matches the next segment's "
                    "start point.  Use the same Python expression rather than separate literals."
                ),
            ))

    return violations


def validate_extrude_depth(
    depth: float,
    *,
    feature_name: str = "",
    min_depth: float = 1e-6,
    max_depth: float | None = None,
) -> list[RuleViolation]:
    """Validate extrude / cut depth before calling SOLIDWORKS.

    Args:
        depth: Requested depth in metres.
        feature_name: Feature label for messages.
        min_depth: Minimum meaningful depth (default 1 µm).
        max_depth: If given, warns when depth exceeds this value.
    """
    violations: list[RuleViolation] = []

    if depth < 0:
        violations.append(RuleViolation(
            rule_name="EXTRUDE_NEGATIVE_DEPTH",
            severity=RuleSeverity.ERROR,
            message=f"Depth {depth * 1000:.3f} mm is negative.",
            feature=feature_name,
            suggested_fix="Use reverse=True to flip direction instead of a negative depth.",
        ))
    elif depth < min_depth:
        violations.append(RuleViolation(
            rule_name="EXTRUDE_NEAR_ZERO_DEPTH",
            severity=RuleSeverity.ERROR,
            message=f"Depth {depth * 1e6:.2f} µm is below the minimum {min_depth * 1e6:.2f} µm.",
            feature=feature_name,
            suggested_fix="Use a positive non-trivial depth.",
        ))

    if max_depth is not None and depth > max_depth:
        violations.append(RuleViolation(
            rule_name="EXTRUDE_EXCEEDS_BODY",
            severity=RuleSeverity.WARNING,
            message=(
                f"Depth {depth * 1000:.3f} mm exceeds the expected body size "
                f"{max_depth * 1000:.3f} mm.  The cut may exit the model."
            ),
            feature=feature_name,
            suggested_fix="Reduce depth or verify the body height first.",
        ))

    return violations


def validate_wall_thickness(
    thickness: float,
    *,
    feature_name: str = "",
    process: DesignProfile = DesignProfile.GENERAL,
) -> list[RuleViolation]:
    """Check a wall thickness value against the process minimum."""
    violations: list[RuleViolation] = []
    minimum = _THRESHOLDS[process]["min_wall_m"]
    if thickness < minimum:
        violations.append(RuleViolation(
            rule_name="WALL_TOO_THIN",
            severity=RuleSeverity.WARNING,
            message=(
                f"Wall thickness {thickness * 1000:.2f} mm is below the "
                f"{_THRESHOLDS[process]['description']} minimum of {minimum * 1000:.2f} mm."
            ),
            feature=feature_name,
            suggested_fix=f"Increase to at least {minimum * 1000:.1f} mm.",
        ))
    return violations


def validate_hole_diameter(
    diameter: float,
    *,
    feature_name: str = "",
    process: DesignProfile = DesignProfile.GENERAL,
) -> list[RuleViolation]:
    """Check a hole / bore diameter against the process minimum."""
    violations: list[RuleViolation] = []
    minimum = _THRESHOLDS[process]["min_hole_m"]
    if diameter < minimum:
        violations.append(RuleViolation(
            rule_name="HOLE_TOO_SMALL",
            severity=RuleSeverity.WARNING,
            message=(
                f"Hole Ø{diameter * 1000:.2f} mm is below the "
                f"{_THRESHOLDS[process]['description']} minimum of Ø{minimum * 1000:.2f} mm."
            ),
            feature=feature_name,
            suggested_fix=f"Increase diameter to at least {minimum * 1000:.1f} mm.",
        ))
    return violations


def validate_fillet_radius(
    radius: float,
    *,
    edge_length: float | None = None,
    feature_name: str = "",
    process: DesignProfile = DesignProfile.GENERAL,
) -> list[RuleViolation]:
    """Check a fillet radius.

    Args:
        radius: Fillet radius in metres.
        edge_length: If provided, warns when radius exceeds half the edge length.
        feature_name: Feature label for messages.
        process: Design profile for minimum radius threshold.
    """
    violations: list[RuleViolation] = []
    minimum = _THRESHOLDS[process]["min_fillet_m"]
    if radius < minimum:
        violations.append(RuleViolation(
            rule_name="FILLET_TOO_SMALL",
            severity=RuleSeverity.WARNING,
            message=(
                f"Fillet radius {radius * 1000:.3f} mm is below the "
                f"{_THRESHOLDS[process]['description']} minimum of {minimum * 1000:.3f} mm."
            ),
            feature=feature_name,
            suggested_fix=f"Increase to at least {minimum * 1000:.2f} mm.",
        ))
    if edge_length is not None and radius > edge_length / 2:
        violations.append(RuleViolation(
            rule_name="FILLET_EXCEEDS_EDGE",
            severity=RuleSeverity.ERROR,
            message=(
                f"Fillet radius {radius * 1000:.3f} mm exceeds half the "
                f"edge length {edge_length * 1000:.3f} mm.  "
                "SOLIDWORKS will reject this fillet."
            ),
            feature=feature_name,
            suggested_fix=f"Use radius ≤ {edge_length / 2 * 1000:.2f} mm.",
        ))
    return violations


def validate_sketch_rectangle(
    x1: float, y1: float, x2: float, y2: float,
    *,
    feature_name: str = "",
    process: DesignProfile = DesignProfile.GENERAL,
) -> list[RuleViolation]:
    """Check a corner rectangle for non-zero area and minimum dimensions."""
    violations: list[RuleViolation] = []
    w = abs(x2 - x1)
    h = abs(y2 - y1)

    if w < 1e-9 or h < 1e-9:
        violations.append(RuleViolation(
            rule_name="SKETCH_DEGENERATE_RECTANGLE",
            severity=RuleSeverity.ERROR,
            message=f"Rectangle has zero {'width' if w < 1e-9 else 'height'} ({w*1000:.3f} × {h*1000:.3f} mm).",
            feature=feature_name,
            suggested_fix="Ensure both corner coordinates differ on both axes.",
        ))

    minimum = _THRESHOLDS[process]["min_wall_m"]
    if 0 < w < minimum:
        violations.append(RuleViolation(
            rule_name="SKETCH_NARROW_FEATURE",
            severity=RuleSeverity.WARNING,
            message=(
                f"Rectangle width {w * 1000:.3f} mm is below the "
                f"{_THRESHOLDS[process]['description']} minimum of {minimum * 1000:.2f} mm."
            ),
            feature=feature_name,
        ))
    if 0 < h < minimum:
        violations.append(RuleViolation(
            rule_name="SKETCH_SHORT_FEATURE",
            severity=RuleSeverity.WARNING,
            message=(
                f"Rectangle height {h * 1000:.3f} mm is below the "
                f"{_THRESHOLDS[process]['description']} minimum of {minimum * 1000:.2f} mm."
            ),
            feature=feature_name,
        ))

    return violations


def validate_circle(
    radius: float,
    *,
    feature_name: str = "",
    process: DesignProfile = DesignProfile.GENERAL,
) -> list[RuleViolation]:
    """Check a sketch circle / bore."""
    violations: list[RuleViolation] = []
    if radius <= 0:
        violations.append(RuleViolation(
            rule_name="SKETCH_NONPOSITIVE_RADIUS",
            severity=RuleSeverity.ERROR,
            message=f"Circle radius {radius * 1000:.3f} mm must be positive.",
            feature=feature_name,
        ))
        return violations
    return validate_hole_diameter(radius * 2, feature_name=feature_name, process=process)


# ---------------------------------------------------------------------------
# DesignChecker — collects violations across a whole model build
# ---------------------------------------------------------------------------

class DesignChecker:
    """Accumulates design-rule violations during a model build session.

    Example::

        checker = DesignChecker(profile=DesignProfile.FDM_PRINTING)

        checker.check_revolve_profile(outer_shell_lines, feature_name="Outer shell")
        checker.check_wall_thickness(mm(1.2), feature_name="Housing wall")
        checker.check_hole(mm(2.5), feature_name="Screw hole")
        checker.check_extrude_depth(mm(50), max_depth=mm(38), feature_name="Deep cut")

        print(checker.report())
        if checker.has_errors():
            raise RuntimeError("Model has design errors — aborting build")
    """

    def __init__(self, profile: DesignProfile = DesignProfile.GENERAL) -> None:
        self.profile = profile
        self.violations: list[RuleViolation] = []

    # ------------------------------------------------------------------
    # Convenience wrappers that add violations to the internal list
    # ------------------------------------------------------------------

    def check_revolve_profile(
        self,
        lines: list[tuple[float, float, float, float]],
        *,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_revolve_profile(lines, feature_name=feature_name)
        self.violations.extend(new)
        return new

    def check_extrude_depth(
        self,
        depth: float,
        *,
        feature_name: str = "",
        max_depth: float | None = None,
    ) -> list[RuleViolation]:
        new = validate_extrude_depth(depth, feature_name=feature_name, max_depth=max_depth)
        self.violations.extend(new)
        return new

    def check_wall_thickness(
        self,
        thickness: float,
        *,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_wall_thickness(thickness, feature_name=feature_name, process=self.profile)
        self.violations.extend(new)
        return new

    def check_hole(
        self,
        diameter: float,
        *,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_hole_diameter(diameter, feature_name=feature_name, process=self.profile)
        self.violations.extend(new)
        return new

    def check_fillet(
        self,
        radius: float,
        *,
        edge_length: float | None = None,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_fillet_radius(
            radius, edge_length=edge_length, feature_name=feature_name, process=self.profile
        )
        self.violations.extend(new)
        return new

    def check_rectangle(
        self,
        x1: float, y1: float, x2: float, y2: float,
        *,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_sketch_rectangle(x1, y1, x2, y2, feature_name=feature_name, process=self.profile)
        self.violations.extend(new)
        return new

    def check_circle(
        self,
        radius: float,
        *,
        feature_name: str = "",
    ) -> list[RuleViolation]:
        new = validate_circle(radius, feature_name=feature_name, process=self.profile)
        self.violations.extend(new)
        return new

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def has_errors(self) -> bool:
        return any(v.severity == RuleSeverity.ERROR for v in self.violations)

    def has_warnings(self) -> bool:
        return any(v.severity == RuleSeverity.WARNING for v in self.violations)

    def errors(self) -> list[RuleViolation]:
        return [v for v in self.violations if v.severity == RuleSeverity.ERROR]

    def warnings(self) -> list[RuleViolation]:
        return [v for v in self.violations if v.severity == RuleSeverity.WARNING]

    def clear(self) -> None:
        self.violations.clear()

    def report(self) -> str:
        """Return a human-readable summary of all collected violations."""
        lines: list[str] = [
            f"Design Rule Check — profile: {_THRESHOLDS[self.profile]['description']}",
            f"  Violations: {len(self.errors())} error(s), {len(self.warnings())} warning(s)",
        ]
        if not self.violations:
            lines.append("  All checks passed.")
        else:
            for v in self.violations:
                lines.append(f"  {v}")
        return "\n".join(lines)

    def assert_ok(self) -> None:
        """Raise RuntimeError if any ERROR violations are present."""
        if self.has_errors():
            raise RuntimeError(
                f"Design validation failed with {len(self.errors())} error(s):\n"
                + "\n".join(f"  {v}" for v in self.errors())
            )
