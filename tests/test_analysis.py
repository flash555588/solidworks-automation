"""Unit tests for enhanced analysis module."""

from __future__ import annotations

from solidworks_com.analysis import (
    GeometryFacts,
    PrecisionLevel,
    ValidationReport,
    ValidationResult,
)


class TestPrecisionLevel:
    def test_tolerances(self) -> None:
        assert PrecisionLevel.COARSE.tolerance_meters == 0.001
        assert PrecisionLevel.STANDARD.tolerance_meters == 0.0001
        assert PrecisionLevel.FINE.tolerance_meters == 0.00001
        assert PrecisionLevel.HIGH.tolerance_meters == 0.000001
        assert PrecisionLevel.ULTRA.tolerance_meters == 0.0000001


class TestGeometryFacts:
    def test_creation(self) -> None:
        facts = GeometryFacts()
        assert facts.bbox_min is None
        assert facts.body_count == 0
        assert facts.volume is None

    def test_to_dict(self) -> None:
        facts = GeometryFacts(
            bbox_min=(0.0, 0.0, 0.0),
            bbox_max=(1.0, 2.0, 3.0),
            size=(1.0, 2.0, 3.0),
            center=(0.5, 1.0, 1.5),
            volume=6.0,
            surface_area=22.0,
            body_count=1,
            solid_count=1,
            feature_count=5,
            projection_area_front=6.0,
            projection_area_top=2.0,
            projection_area_side=3.0,
        )
        d = facts.to_dict()
        assert d["bbox"]["min"] == [0.0, 0.0, 0.0]
        assert d["size"] == [1.0, 2.0, 3.0]
        assert d["volume"] == 6.0
        assert d["surfaceArea"] == 22.0
        assert d["bodyCount"] == 1
        assert d["solidCount"] == 1
        assert d["featureCount"] == 5
        assert d["projectionAreaFront"] == 6.0
        assert d["projectionAreaTop"] == 2.0
        assert d["projectionAreaSide"] == 3.0


class TestGeometryAnalyzerProjection:
    # v0.2: verify that GeometryAnalyzer computes projection
    # areas from the bounding box.

    def test_projection_areas_from_bbox(self) -> None:
        from solidworks_com.analysis import GeometryAnalyzer

        class _MockModel:
            class _Ext:
                def GetBox(self):
                    return (0.0, 0.0, 0.0, 2.0, 3.0, 4.0)
            class _Com:
                pass
            com = _Com()
            com.Extension = _Ext()
            def bodies(self):
                return []
            def iter_features(self):
                return iter([])
            def feature_errors(self):
                return []

        analyzer = GeometryAnalyzer(_MockModel())
        facts = analyzer.extract_facts()
        assert facts.projection_area_front == 12.0  # 3*4
        assert facts.projection_area_top == 6.0     # 2*3
        assert facts.projection_area_side == 8.0    # 2*4

    def test_projection_areas_none_when_no_bbox(self) -> None:
        from solidworks_com.analysis import GeometryAnalyzer

        class _MockModel:
            class _Com:
                pass
            com = _Com()
            def bodies(self):
                return []
            def iter_features(self):
                return iter([])
            def feature_errors(self):
                return []

        analyzer = GeometryAnalyzer(_MockModel())
        facts = analyzer.extract_facts()
        assert facts.projection_area_front is None
        assert facts.projection_area_top is None
        assert facts.projection_area_side is None


class TestValidationResult:
    def test_passed(self) -> None:
        r = ValidationResult(check_name="size_x", passed=True, expected=1.0, actual=1.0)
        assert r.passed is True
        assert r.severity == "error"

    def test_failed(self) -> None:
        r = ValidationResult(
            check_name="size_x",
            passed=False,
            expected=1.0,
            actual=0.5,
            tolerance=0.001,
            message="Size mismatch",
            severity="warning",
        )
        assert r.passed is False
        assert r.severity == "warning"

    def test_to_dict(self) -> None:
        r = ValidationResult(check_name="test", passed=True, severity="info")
        d = r.to_dict()
        assert d["check"] == "test"
        assert d["passed"] is True
        assert d["severity"] == "info"


class TestValidationReport:
    def test_empty_report(self) -> None:
        r = ValidationReport()
        assert r.success is True
        assert r.has_warnings is False

    def test_add_results(self) -> None:
        r = ValidationReport()
        r.add_result(ValidationResult(check_name="test1", passed=True))
        r.add_result(ValidationResult(check_name="test2", passed=False, message="failed"))
        r.add_result(ValidationResult(check_name="test3", passed=False, severity="warning", message="warn"))
        assert r.total_checks == 3
        assert r.passed_checks == 1
        assert r.failed_checks == 1
        assert r.warning_checks == 1
        assert r.success is False
        assert r.has_warnings is True

    def test_precision_level(self) -> None:
        r = ValidationReport(precision_level=PrecisionLevel.HIGH)
        assert r.precision_level == PrecisionLevel.HIGH

    def test_summary(self) -> None:
        r = ValidationReport(model_name="test_model", precision_level=PrecisionLevel.STANDARD)
        r.add_result(ValidationResult(check_name="size", passed=True))
        s = r.summary()
        assert "test_model" in s
        assert "STANDARD" in s
        assert "1/1 passed" in s

    def test_to_dict(self) -> None:
        r = ValidationReport(model_name="test", precision_level=PrecisionLevel.FINE)
        d = r.to_dict()
        assert d["model"] == "test"
        assert d["precisionLevel"] == "FINE"
        assert d["summary"]["success"] is True
