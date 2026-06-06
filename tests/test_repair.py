"""Unit tests for solidworks_com.repair (no SOLIDWORKS required)."""

from __future__ import annotations

import pytest

from solidworks_com.repair import (
    FailureClass,
    RepairAnalyzer,
    RepairReport,
    RepairSuggestion,
    analyze_error,
)


class TestRepairSuggestion:
    def test_to_dict_keys(self) -> None:
        s = RepairSuggestion(
            failure_class=FailureClass.EXTRUDE_FAILED,
            description="Extrusion failed",
            suggested_fix="Check sketch is closed.",
            confidence=0.8,
        )
        d = s.to_dict()
        for key in ("failure_class", "description", "suggested_fix", "confidence", "related_code"):
            assert key in d

    def test_failure_class_name_in_dict(self) -> None:
        s = RepairSuggestion(FailureClass.CUT_FAILED, "d", "f", 0.5)
        assert s.to_dict()["failure_class"] == "CUT_FAILED"

    def test_related_code_none_by_default(self) -> None:
        s = RepairSuggestion(FailureClass.UNKNOWN, "d", "f", 0.3)
        assert s.to_dict()["related_code"] is None


class TestRepairReport:
    def _make_report(self) -> RepairReport:
        return RepairReport(
            original_error="extrude failed: no contour",
            failure_class=FailureClass.EXTRUDE_FAILED,
            suggestions=[
                RepairSuggestion(FailureClass.EXTRUDE_FAILED, "desc1", "fix1", 0.9),
                RepairSuggestion(FailureClass.EXTRUDE_FAILED, "desc2", "fix2", 0.5),
            ],
        )

    def test_has_suggestions_true(self) -> None:
        assert self._make_report().has_suggestions is True

    def test_has_suggestions_false_when_empty(self) -> None:
        r = RepairReport("err", FailureClass.UNKNOWN, [])
        assert r.has_suggestions is False

    def test_best_suggestion_highest_confidence(self) -> None:
        report = self._make_report()
        best = report.best_suggestion
        assert best is not None
        assert best.confidence == pytest.approx(0.9)

    def test_best_suggestion_none_when_no_suggestions(self) -> None:
        r = RepairReport("err", FailureClass.UNKNOWN, [])
        assert r.best_suggestion is None

    def test_to_dict_keys(self) -> None:
        d = self._make_report().to_dict()
        for key in ("original_error", "failure_class", "suggestions", "has_suggestions"):
            assert key in d

    def test_summary_contains_failure_class(self) -> None:
        s = self._make_report().summary()
        assert "EXTRUDE_FAILED" in s

    def test_summary_contains_suggestions(self) -> None:
        s = self._make_report().summary()
        assert "desc1" in s


class TestRepairAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = RepairAnalyzer()

    def test_classify_sketch_not_closed(self) -> None:
        assert self.analyzer.classify_error("not closed") == FailureClass.SKETCH_NOT_CLOSED

    def test_classify_extrude(self) -> None:
        assert self.analyzer.classify_error("extrude failed") == FailureClass.EXTRUDE_FAILED

    def test_classify_extrusion(self) -> None:
        assert self.analyzer.classify_error("extrusion error") == FailureClass.EXTRUDE_FAILED

    def test_classify_cut(self) -> None:
        assert self.analyzer.classify_error("cut operation failed") == FailureClass.CUT_FAILED

    def test_classify_fillet(self) -> None:
        assert self.analyzer.classify_error("fillet too large") == FailureClass.FILLET_TOO_LARGE

    def test_classify_loft(self) -> None:
        assert self.analyzer.classify_error("loft profiles incompatible") == FailureClass.LOFT_FAILED

    def test_classify_revolve(self) -> None:
        assert self.analyzer.classify_error("revolve failed") == FailureClass.REVOLVE_FAILED

    def test_classify_plane_not_found(self) -> None:
        assert self.analyzer.classify_error("plane not found") == FailureClass.PLANE_NOT_FOUND

    def test_classify_save(self) -> None:
        assert self.analyzer.classify_error("save failed") == FailureClass.SAVE_FAILED

    def test_classify_rebuild(self) -> None:
        assert self.analyzer.classify_error("rebuild error") == FailureClass.REBUILD_ERROR

    def test_classify_unknown(self) -> None:
        assert self.analyzer.classify_error("something completely different") == FailureClass.UNKNOWN

    def test_classify_case_insensitive(self) -> None:
        assert self.analyzer.classify_error("EXTRUDE FAILED") == FailureClass.EXTRUDE_FAILED

    def test_analyze_returns_report(self) -> None:
        report = self.analyzer.analyze("extrude failed: no contour")
        assert isinstance(report, RepairReport)

    def test_analyze_has_suggestions(self) -> None:
        report = self.analyzer.analyze("extrude failed")
        assert report.has_suggestions

    def test_analyze_unknown_has_generic_suggestion(self) -> None:
        report = self.analyzer.analyze("xyzzy")
        assert report.has_suggestions
        assert report.failure_class == FailureClass.UNKNOWN

    def test_analyze_sketch_not_closed_suggestions(self) -> None:
        report = self.analyzer.analyze("sketch is not closed")
        assert report.failure_class == FailureClass.SKETCH_NOT_CLOSED
        assert len(report.suggestions) >= 1

    def test_analyze_context_passed_through(self) -> None:
        ctx = {"feature": "extrude1"}
        report = self.analyzer.analyze("extrude failed", context=ctx)
        assert report.context == ctx


class TestAnalyzeError:
    def test_returns_repair_report(self) -> None:
        report = analyze_error("fillet radius too large")
        assert isinstance(report, RepairReport)

    def test_fillet_classified_correctly(self) -> None:
        report = analyze_error("fillet radius too large")
        assert report.failure_class == FailureClass.FILLET_TOO_LARGE

    def test_with_feature_type(self) -> None:
        report = analyze_error("failed", feature_type="extrude")
        assert isinstance(report, RepairReport)
