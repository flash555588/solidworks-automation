"""Repair loop diagnostics for SOLIDWORKS feature failures.

Inspired by text-to-cad's repair-loop principles:
- Read the failing command output
- Classify the failure
- Make the smallest responsible source change
- Rerun and validate
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class FailureClass(Enum):
    """Classification of feature failures."""

    SKETCH_NOT_CLOSED = auto()
    SKETCH_INVALID = auto()
    EXTRUDE_FAILED = auto()
    CUT_FAILED = auto()
    FILLET_TOO_LARGE = auto()
    CHAMFER_TOO_LARGE = auto()
    BOOLEAN_FAILED = auto()
    LOFT_FAILED = auto()
    SWEEP_FAILED = auto()
    REVOLVE_FAILED = auto()
    DIMENSION_INVALID = auto()
    SELECTION_FAILED = auto()
    PLANE_NOT_FOUND = auto()
    FEATURE_SUPPRESSED = auto()
    REBUILD_ERROR = auto()
    SAVE_FAILED = auto()
    EXPORT_FAILED = auto()
    UNKNOWN = auto()


@dataclass
class RepairSuggestion:
    """A suggestion for fixing a feature failure."""

    failure_class: FailureClass
    description: str
    suggested_fix: str
    confidence: float  # 0.0 to 1.0
    related_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class.name,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
            "related_code": self.related_code,
        }


@dataclass
class RepairReport:
    """Report from repair loop analysis."""

    original_error: str
    failure_class: FailureClass
    suggestions: list[RepairSuggestion]
    context: dict[str, Any] | None = None

    @property
    def has_suggestions(self) -> bool:
        return len(self.suggestions) > 0

    @property
    def best_suggestion(self) -> RepairSuggestion | None:
        if not self.suggestions:
            return None
        return max(self.suggestions, key=lambda s: s.confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_error": self.original_error,
            "failure_class": self.failure_class.name,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "has_suggestions": self.has_suggestions,
        }

    def summary(self) -> str:
        """Generate human-readable repair report."""
        lines = [f"Repair Report: {self.failure_class.name}"]
        lines.append(f"  Error: {self.original_error}")

        if self.suggestions:
            lines.append(f"  Suggestions ({len(self.suggestions)}):")
            for i, s in enumerate(self.suggestions, 1):
                lines.append(f"    {i}. {s.description}")
                lines.append(f"       Fix: {s.suggested_fix}")
                lines.append(f"       Confidence: {s.confidence:.0%}")
        else:
            lines.append("  No suggestions available")

        return "\n".join(lines)


class RepairAnalyzer:
    """Analyzes feature failures and suggests repairs."""

    # Error pattern to failure class mapping (more specific patterns first)
    ERROR_PATTERNS: list[tuple[str, FailureClass]] = [
        # Specific patterns first
        ("not closed", FailureClass.SKETCH_NOT_CLOSED),
        ("sketch is not closed", FailureClass.SKETCH_NOT_CLOSED),
        ("open sketch", FailureClass.SKETCH_NOT_CLOSED),
        # Generic patterns after
        ("sketch", FailureClass.SKETCH_INVALID),
        ("extrude", FailureClass.EXTRUDE_FAILED),
        ("extrusion", FailureClass.EXTRUDE_FAILED),
        ("cut", FailureClass.CUT_FAILED),
        ("fillet", FailureClass.FILLET_TOO_LARGE),
        ("chamfer", FailureClass.CHAMFER_TOO_LARGE),
        ("boolean", FailureClass.BOOLEAN_FAILED),
        ("loft", FailureClass.LOFT_FAILED),
        ("sweep", FailureClass.SWEEP_FAILED),
        ("revolve", FailureClass.REVOLVE_FAILED),
        ("dimension", FailureClass.DIMENSION_INVALID),
        ("select", FailureClass.SELECTION_FAILED),
        ("plane", FailureClass.PLANE_NOT_FOUND),
        ("suppress", FailureClass.FEATURE_SUPPRESSED),
        ("rebuild", FailureClass.REBUILD_ERROR),
        ("save", FailureClass.SAVE_FAILED),
        ("export", FailureClass.EXPORT_FAILED),
    ]

    def classify_error(self, error_message: str) -> FailureClass:
        """Classify an error message into a failure class."""
        error_lower = error_message.lower()

        for pattern, failure_class in self.ERROR_PATTERNS:
            if pattern in error_lower:
                return failure_class

        return FailureClass.UNKNOWN

    def analyze(
        self,
        error_message: str,
        *,
        feature_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> RepairReport:
        """Analyze an error and generate repair suggestions."""
        failure_class = self.classify_error(error_message)
        suggestions = self._generate_suggestions(failure_class, error_message, context)

        return RepairReport(
            original_error=error_message,
            failure_class=failure_class,
            suggestions=suggestions,
            context=context,
        )

    def _generate_suggestions(
        self,
        failure_class: FailureClass,
        error_message: str,
        context: dict[str, Any] | None,
    ) -> list[RepairSuggestion]:
        """Generate repair suggestions based on failure class."""
        suggestions = []

        if failure_class == FailureClass.SKETCH_NOT_CLOSED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Sketch profile is not closed",
                suggested_fix="Ensure all sketch segments form a closed loop. Check for gaps at segment endpoints.",
                confidence=0.9,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Sketch has overlapping segments",
                suggested_fix="Remove duplicate or overlapping segments that prevent proper closure.",
                confidence=0.7,
            ))

        elif failure_class == FailureClass.EXTRUDE_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Extrusion failed - no valid sketch contour",
                suggested_fix="Verify sketch has a closed contour. Try selecting the contour explicitly before extruding.",
                confidence=0.8,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Extrusion direction or depth invalid",
                suggested_fix="Check extrusion depth is positive and direction is correct. Try reverse=True if needed.",
                confidence=0.6,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Merge conflict with existing body",
                suggested_fix="If merging, ensure the extrusion intersects with the target body. Try merge=False first.",
                confidence=0.5,
            ))

        elif failure_class == FailureClass.CUT_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Cut feature failed - tool doesn't intersect target",
                suggested_fix="Ensure the cut profile passes through or into the target body. Increase cut depth for through-cuts.",
                confidence=0.8,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Cut depth insufficient",
                suggested_fix="Use cut_midplane() for through-cuts, or increase cut_blind() depth to exceed body thickness.",
                confidence=0.7,
            ))

        elif failure_class == FailureClass.FILLET_TOO_LARGE:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Fillet radius exceeds local geometry",
                suggested_fix="Reduce fillet radius to be smaller than the smallest adjacent edge or face.",
                confidence=0.9,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Selected edges include unintended small edges",
                suggested_fix="Filter edge selection more narrowly to exclude small or unintended edges.",
                confidence=0.6,
            ))

        elif failure_class == FailureClass.LOFT_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Loft failed - profiles may be incompatible",
                suggested_fix="Ensure both profiles have the same number of segments and compatible topology.",
                confidence=0.7,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Loft guide curves may be needed",
                suggested_fix="Add guide curves to control the loft shape between profiles.",
                confidence=0.5,
            ))

        elif failure_class == FailureClass.BOOLEAN_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Boolean operation failed - bodies may not intersect",
                suggested_fix="Ensure the tool body intersects with the target body. Check positioning.",
                confidence=0.8,
            ))

        elif failure_class == FailureClass.SELECTION_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Selection failed - object not found",
                suggested_fix="Verify the object name, type, and position. Use clear_selection() before new selections.",
                confidence=0.7,
            ))

        elif failure_class == FailureClass.SAVE_FAILED:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Save failed - document may not be active",
                suggested_fix="Call activate() and clear_selection() before save_as().",
                confidence=0.9,
            ))
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Save failed - path encoding issue",
                suggested_fix="Use ASCII-only paths or ensure proper Unicode handling for paths with special characters.",
                confidence=0.6,
            ))

        elif failure_class == FailureClass.REBUILD_ERROR:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Rebuild error - features have errors",
                suggested_fix="Check feature_errors() to identify which features have errors and fix them individually.",
                confidence=0.8,
            ))

        # Add generic suggestion if none specific
        if not suggestions:
            suggestions.append(RepairSuggestion(
                failure_class=failure_class,
                description="Unknown error occurred",
                suggested_fix="Check the error message and SOLIDWORKS feature tree for more details. Try rebuilding the model.",
                confidence=0.3,
            ))

        return suggestions


def analyze_error(
    error_message: str,
    *,
    feature_type: str | None = None,
    context: dict[str, Any] | None = None,
) -> RepairReport:
    """Convenience function to analyze an error.

    Example::

        try:
            part.features.extrude_blind(depth)
        except SolidWorksError as e:
            report = analyze_error(str(e), feature_type="extrude")
            print(report.summary())
            if report.best_suggestion:
                print(f"Try: {report.best_suggestion.suggested_fix}")
    """
    analyzer = RepairAnalyzer()
    return analyzer.analyze(error_message, feature_type=feature_type, context=context)
