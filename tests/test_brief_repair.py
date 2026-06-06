"""Unit tests for brief and repair modules."""

from __future__ import annotations

from solidworks_com.brief import CABBrief, parse_brief
from solidworks_com.repair import FailureClass, RepairAnalyzer, analyze_error


class TestCABBrief:
    def test_creation(self) -> None:
        brief = CABBrief(model_name="test_part")
        assert brief.model_name == "test_part"
        assert brief.units == "mm"

    def test_to_dict(self) -> None:
        brief = CABBrief(model_name="test", width=100.0, height=50.0)
        d = brief.to_dict()
        assert d["model_name"] == "test"
        assert d["dimensions"]["width"] == 100.0

    def test_summary(self) -> None:
        brief = CABBrief(model_name="test", width=100.0, height=50.0, depth=10.0)
        s = brief.summary()
        assert "test" in s
        assert "W=100.0" in s


class TestBriefParser:
    def test_parse_plate(self) -> None:
        text = "Make a 100mm by 60mm by 6mm mounting plate with four 4.5mm holes"
        brief = parse_brief(text)
        assert brief.width == 100.0
        assert brief.height == 60.0
        assert brief.depth == 6.0
        assert len(brief.holes) == 4

    def test_parse_bracket(self) -> None:
        text = "Create an L-bracket with rounded corners and two M4 holes"
        brief = parse_brief(text)
        assert "bracket" in brief.model_name.lower()
        assert len(brief.fillets) > 0

    def test_parse_dimensions(self) -> None:
        text = "A cylinder with diameter 20mm and thickness 5mm"
        brief = parse_brief(text)
        assert brief.diameter == 20.0
        assert brief.thickness == 5.0

    def test_parse_chamfer(self) -> None:
        text = "Add 2mm chamfer on the edges"
        brief = parse_brief(text)
        assert len(brief.chamfers) > 0
        assert brief.chamfers[0]["size"] == 2.0

    def test_no_dimensions_clarification(self) -> None:
        text = "Make a bracket"
        brief = parse_brief(text)
        assert brief.clarification_needed is not None


class TestRepairAnalyzer:
    def test_classify_sketch_error(self) -> None:
        analyzer = RepairAnalyzer()
        fc = analyzer.classify_error("Sketch is not closed")
        assert fc == FailureClass.SKETCH_NOT_CLOSED

    def test_classify_extrude_error(self) -> None:
        analyzer = RepairAnalyzer()
        fc = analyzer.classify_error("Failed to create blind extrusion")
        assert fc == FailureClass.EXTRUDE_FAILED

    def test_classify_fillet_error(self) -> None:
        analyzer = RepairAnalyzer()
        fc = analyzer.classify_error("Fillet radius too large")
        assert fc == FailureClass.FILLET_TOO_LARGE

    def test_classify_save_error(self) -> None:
        analyzer = RepairAnalyzer()
        fc = analyzer.classify_error("Failed to save document")
        assert fc == FailureClass.SAVE_FAILED

    def test_classify_unknown(self) -> None:
        analyzer = RepairAnalyzer()
        fc = analyzer.classify_error("Some random error")
        assert fc == FailureClass.UNKNOWN

    def test_analyze_extrude_error(self) -> None:
        report = analyze_error("Failed to create blind extrusion")
        assert report.failure_class == FailureClass.EXTRUDE_FAILED
        assert report.has_suggestions
        assert report.best_suggestion is not None

    def test_analyze_save_error(self) -> None:
        report = analyze_error("Failed to save document as: test.SLDPRT")
        assert report.failure_class == FailureClass.SAVE_FAILED
        assert report.has_suggestions

    def test_report_summary(self) -> None:
        report = analyze_error("Fillet radius too large")
        s = report.summary()
        assert "FILLET_TOO_LARGE" in s
        assert "suggestions" in s.lower() or "Suggestion" in s

    def test_suggestion_to_dict(self) -> None:
        report = analyze_error("Failed to create blind extrusion")
        if report.best_suggestion:
            d = report.best_suggestion.to_dict()
            assert "failure_class" in d
            assert "suggested_fix" in d
