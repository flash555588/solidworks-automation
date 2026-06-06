"""Unit tests for solidworks_com.design_rules."""

from __future__ import annotations

import pytest

from solidworks_com.design_rules import (
    DesignChecker,
    DesignProfile,
    RuleSeverity,
    RuleViolation,
    validate_circle,
    validate_extrude_depth,
    validate_fillet_radius,
    validate_hole_diameter,
    validate_revolve_profile,
    validate_sketch_rectangle,
    validate_wall_thickness,
)
from solidworks_com.units import mm

# ---------------------------------------------------------------------------
# validate_revolve_profile
# ---------------------------------------------------------------------------

class TestValidateRevolveProfile:
    def test_valid_open_profile_passes(self) -> None:
        # Flashlight-style: starts at X=0, goes out, comes back — no axis line
        lines = [
            (mm(0),  mm(0),  mm(13), mm(0)),
            (mm(13), mm(0),  mm(13), mm(15)),
            (mm(13), mm(15), mm(0),  mm(15)),
        ]
        assert validate_revolve_profile(lines) == []

    def test_axis_closing_line_raises_error(self) -> None:
        # Closing line along X=0 — the classic revolve failure
        lines = [
            (mm(0),  mm(0),  mm(13), mm(0)),
            (mm(13), mm(0),  mm(13), mm(15)),
            (mm(13), mm(15), mm(0),  mm(15)),
            (mm(0),  mm(15), mm(0),  mm(0)),   # ← axis-closing line
        ]
        violations = validate_revolve_profile(lines)
        assert any(v.rule_name == "REVOLVE_NO_AXIS_LINE" for v in violations)
        assert any(v.severity == RuleSeverity.ERROR for v in violations)

    def test_negative_x_raises_error(self) -> None:
        lines = [
            (mm(-5), mm(0),  mm(13), mm(0)),
            (mm(13), mm(0),  mm(13), mm(15)),
        ]
        violations = validate_revolve_profile(lines)
        assert any(v.rule_name == "REVOLVE_PROFILE_CROSSES_AXIS" for v in violations)

    def test_zero_length_segment_raises_error(self) -> None:
        lines = [
            (mm(5), mm(0), mm(5), mm(0)),   # zero-length
            (mm(5), mm(0), mm(5), mm(10)),
        ]
        violations = validate_revolve_profile(lines)
        assert any(v.rule_name == "SKETCH_ZERO_LENGTH_SEGMENT" for v in violations)

    def test_disconnected_profile_warns(self) -> None:
        lines = [
            (mm(0), mm(0),  mm(10), mm(0)),
            (mm(11), mm(0), mm(11), mm(10)),   # 1 mm gap from previous end
        ]
        violations = validate_revolve_profile(lines)
        assert any(v.rule_name == "SKETCH_DISCONNECTED_PROFILE" for v in violations)
        assert any(v.severity == RuleSeverity.WARNING for v in violations)

    def test_feature_name_in_message(self) -> None:
        lines = [(mm(0), mm(0), mm(0), mm(10))]   # axis line
        violations = validate_revolve_profile(lines, feature_name="Test feature")
        assert all(v.feature == "Test feature" for v in violations)

    def test_empty_profile_passes(self) -> None:
        assert validate_revolve_profile([]) == []


# ---------------------------------------------------------------------------
# validate_extrude_depth
# ---------------------------------------------------------------------------

class TestValidateExtrudeDepth:
    def test_positive_depth_passes(self) -> None:
        assert validate_extrude_depth(mm(10)) == []

    def test_zero_depth_is_error(self) -> None:
        violations = validate_extrude_depth(0.0)
        assert any(v.severity == RuleSeverity.ERROR for v in violations)

    def test_negative_depth_is_error(self) -> None:
        violations = validate_extrude_depth(mm(-5))
        assert any(v.rule_name == "EXTRUDE_NEGATIVE_DEPTH" for v in violations)

    def test_exceeds_max_warns(self) -> None:
        violations = validate_extrude_depth(mm(50), max_depth=mm(38))
        assert any(v.rule_name == "EXTRUDE_EXCEEDS_BODY" for v in violations)
        assert any(v.severity == RuleSeverity.WARNING for v in violations)

    def test_within_max_passes(self) -> None:
        assert validate_extrude_depth(mm(30), max_depth=mm(38)) == []


# ---------------------------------------------------------------------------
# validate_wall_thickness
# ---------------------------------------------------------------------------

class TestValidateWallThickness:
    def test_adequate_thickness_passes(self) -> None:
        assert validate_wall_thickness(mm(2.0), process=DesignProfile.FDM_PRINTING) == []

    def test_too_thin_warns(self) -> None:
        # FDM min is 1.5 mm; 0.8 mm should warn
        violations = validate_wall_thickness(mm(0.8), process=DesignProfile.FDM_PRINTING)
        assert any(v.rule_name == "WALL_TOO_THIN" for v in violations)

    def test_general_profile_less_strict(self) -> None:
        # General min is 0.5 mm; 0.8 mm should pass
        assert validate_wall_thickness(mm(0.8), process=DesignProfile.GENERAL) == []

    def test_machining_min_wall(self) -> None:
        violations = validate_wall_thickness(mm(0.5), process=DesignProfile.MACHINING)
        assert any(v.rule_name == "WALL_TOO_THIN" for v in violations)


# ---------------------------------------------------------------------------
# validate_hole_diameter
# ---------------------------------------------------------------------------

class TestValidateHoleDiameter:
    def test_large_hole_passes(self) -> None:
        assert validate_hole_diameter(mm(6), process=DesignProfile.MACHINING) == []

    def test_small_hole_warns(self) -> None:
        # Machining min is 3 mm
        violations = validate_hole_diameter(mm(2), process=DesignProfile.MACHINING)
        assert any(v.rule_name == "HOLE_TOO_SMALL" for v in violations)


# ---------------------------------------------------------------------------
# validate_fillet_radius
# ---------------------------------------------------------------------------

class TestValidateFilletRadius:
    def test_valid_radius_passes(self) -> None:
        assert validate_fillet_radius(mm(2)) == []

    def test_radius_exceeds_half_edge_is_error(self) -> None:
        violations = validate_fillet_radius(mm(10), edge_length=mm(15))
        assert any(v.rule_name == "FILLET_EXCEEDS_EDGE" for v in violations)
        assert any(v.severity == RuleSeverity.ERROR for v in violations)

    def test_radius_within_half_edge_passes(self) -> None:
        assert validate_fillet_radius(mm(5), edge_length=mm(15)) == []


# ---------------------------------------------------------------------------
# validate_sketch_rectangle
# ---------------------------------------------------------------------------

class TestValidateSketchRectangle:
    def test_normal_rect_passes(self) -> None:
        assert validate_sketch_rectangle(mm(-10), mm(0), mm(10), mm(20)) == []

    def test_zero_width_is_error(self) -> None:
        violations = validate_sketch_rectangle(mm(5), mm(0), mm(5), mm(10))
        assert any(v.rule_name == "SKETCH_DEGENERATE_RECTANGLE" for v in violations)

    def test_zero_height_is_error(self) -> None:
        violations = validate_sketch_rectangle(mm(0), mm(5), mm(10), mm(5))
        assert any(v.rule_name == "SKETCH_DEGENERATE_RECTANGLE" for v in violations)

    def test_narrow_warns_for_fdm(self) -> None:
        # FDM min is 1.5 mm; 1 mm wide should warn
        violations = validate_sketch_rectangle(
            mm(0), mm(0), mm(1), mm(20), process=DesignProfile.FDM_PRINTING
        )
        assert any(v.rule_name == "SKETCH_NARROW_FEATURE" for v in violations)


# ---------------------------------------------------------------------------
# validate_circle
# ---------------------------------------------------------------------------

class TestValidateCircle:
    def test_positive_radius_passes(self) -> None:
        assert validate_circle(mm(5)) == []

    def test_zero_radius_is_error(self) -> None:
        violations = validate_circle(0.0)
        assert any(v.severity == RuleSeverity.ERROR for v in violations)

    def test_negative_radius_is_error(self) -> None:
        violations = validate_circle(mm(-3))
        assert any(v.severity == RuleSeverity.ERROR for v in violations)


# ---------------------------------------------------------------------------
# DesignChecker
# ---------------------------------------------------------------------------

class TestDesignChecker:
    def test_no_violations_initially(self) -> None:
        chk = DesignChecker()
        assert chk.violations == []
        assert not chk.has_errors()

    def test_accumulates_violations(self) -> None:
        chk = DesignChecker(profile=DesignProfile.MACHINING)
        lines_with_axis = [
            (mm(0), mm(0), mm(0), mm(10)),   # axis line
        ]
        chk.check_revolve_profile(lines_with_axis, feature_name="Feat A")
        chk.check_wall_thickness(mm(0.4), feature_name="Feat B")
        assert len(chk.violations) >= 2

    def test_has_errors_returns_true_on_error(self) -> None:
        chk = DesignChecker()
        chk.check_extrude_depth(mm(-5), feature_name="bad")
        assert chk.has_errors()

    def test_assert_ok_raises_on_error(self) -> None:
        chk = DesignChecker()
        chk.check_extrude_depth(mm(-5))
        with pytest.raises(RuntimeError, match="Design validation failed"):
            chk.assert_ok()

    def test_assert_ok_passes_on_warnings_only(self) -> None:
        chk = DesignChecker(profile=DesignProfile.FDM_PRINTING)
        chk.check_wall_thickness(mm(0.8))   # warning, not error
        chk.assert_ok()   # should not raise

    def test_clear_resets_violations(self) -> None:
        chk = DesignChecker()
        chk.check_extrude_depth(mm(-1))
        assert chk.has_errors()
        chk.clear()
        assert not chk.has_errors()
        assert chk.violations == []

    def test_report_contains_profile_name(self) -> None:
        chk = DesignChecker(profile=DesignProfile.INJECTION_MOLDING)
        report = chk.report()
        assert "injection" in report.lower() or "moulding" in report.lower()

    def test_report_no_violations(self) -> None:
        chk = DesignChecker()
        report = chk.report()
        assert "passed" in report.lower()

    def test_all_check_methods_return_violations(self) -> None:
        chk = DesignChecker(profile=DesignProfile.FDM_PRINTING)
        chk.check_revolve_profile([(mm(0), mm(0), mm(0), mm(5))])
        chk.check_extrude_depth(mm(-1))
        chk.check_wall_thickness(mm(0.2))
        chk.check_hole(mm(0.5))
        chk.check_fillet(mm(20), edge_length=mm(5))
        chk.check_rectangle(mm(5), mm(5), mm(5), mm(5))
        chk.check_circle(mm(-1))
        assert len(chk.violations) >= 7


# ---------------------------------------------------------------------------
# RuleViolation __str__
# ---------------------------------------------------------------------------

class TestRuleViolationStr:
    def test_error_prefix(self) -> None:
        v = RuleViolation("R1", RuleSeverity.ERROR, "something broke")
        assert "[ERROR]" in str(v)

    def test_feature_included_when_set(self) -> None:
        v = RuleViolation("R1", RuleSeverity.WARNING, "msg", feature="Outer shell")
        assert "Outer shell" in str(v)

    def test_fix_included_when_set(self) -> None:
        v = RuleViolation("R1", RuleSeverity.INFO, "msg", suggested_fix="do this")
        assert "do this" in str(v)
