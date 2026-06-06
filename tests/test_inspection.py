"""Unit tests for solidworks_com.inspection."""

from __future__ import annotations

from solidworks_com.inspection import BoundingBox, FeatureInfo, InspectionReport


class TestBoundingBox:
    def test_creation(self) -> None:
        bb = BoundingBox(0, 0, 0, 10, 20, 30)
        assert bb.width == 10
        assert bb.height == 20
        assert bb.depth == 30

    def test_center(self) -> None:
        bb = BoundingBox(0, 0, 0, 10, 20, 30)
        assert bb.center == (5.0, 10.0, 15.0)

    def test_volume(self) -> None:
        bb = BoundingBox(0, 0, 0, 10, 20, 30)
        assert bb.volume == 6000

    def test_contains_point(self) -> None:
        bb = BoundingBox(0, 0, 0, 10, 20, 30)
        assert bb.contains_point(5, 10, 15) is True
        assert bb.contains_point(0, 0, 0) is True
        assert bb.contains_point(10, 20, 30) is True
        assert bb.contains_point(15, 10, 15) is False

    def test_overlaps(self) -> None:
        bb1 = BoundingBox(0, 0, 0, 10, 10, 10)
        bb2 = BoundingBox(5, 5, 5, 15, 15, 15)
        bb3 = BoundingBox(20, 20, 20, 30, 30, 30)
        assert bb1.overlaps(bb2) is True
        assert bb1.overlaps(bb3) is False

    def test_to_dict(self) -> None:
        bb = BoundingBox(0, 0, 0, 10, 20, 30)
        d = bb.to_dict()
        assert d["width"] == 10
        assert d["height"] == 20
        assert d["depth"] == 30


class TestFeatureInfo:
    def test_creation(self) -> None:
        f = FeatureInfo(name="Extrude1", type_name="Extrusion")
        assert f.name == "Extrude1"
        assert f.has_error is False

    def test_with_error(self) -> None:
        f = FeatureInfo(name="Fillet1", type_name="Fillet", error_code=1)
        assert f.has_error is True

    def test_to_dict(self) -> None:
        f = FeatureInfo(name="Extrude1", type_name="Extrusion")
        d = f.to_dict()
        assert d["name"] == "Extrude1"
        assert d["has_error"] is False


class TestInspectionReport:
    def test_empty_report(self) -> None:
        r = InspectionReport()
        assert r.has_errors is False

    def test_with_validation_issues(self) -> None:
        r = InspectionReport(validation_issues=["Width mismatch"])
        assert r.has_errors is True

    def test_with_feature_errors(self) -> None:
        r = InspectionReport(features=[
            FeatureInfo("Extrude1", "Extrusion"),
            FeatureInfo("Fillet1", "Fillet", error_code=1),
        ])
        assert r.has_errors is True

    def test_summary(self) -> None:
        r = InspectionReport(
            bounding_box=BoundingBox(0, 0, 0, 10, 20, 30),
            body_count=1,
            validation_issues=["Test issue"],
        )
        s = r.summary()
        assert "Bounding Box" in s
        assert "Bodies: 1" in s
        assert "Test issue" in s

    def test_to_dict(self) -> None:
        r = InspectionReport(body_count=1)
        d = r.to_dict()
        assert d["body_count"] == 1
        assert d["has_errors"] is False
