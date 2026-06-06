"""Unit tests for precision module."""

from __future__ import annotations

from solidworks_com.precision import (
    MeshQuality,
    MeshSettings,
    PrecisionSettings,
    PrecisionValidator,
    create_precision_validator,
)


class TestMeshQuality:
    def test_draft(self) -> None:
        q = MeshQuality.DRAFT
        assert q.linear_deflection == 0.01
        assert q.angular_deflection == 0.5

    def test_ultra(self) -> None:
        q = MeshQuality.ULTRA
        assert q.linear_deflection == 0.0005
        assert q.angular_deflection == 0.05

    def test_description(self) -> None:
        assert "Draft" in MeshQuality.DRAFT.description
        assert "Ultra" in MeshQuality.ULTRA.description


class TestMeshSettings:
    def test_from_quality(self) -> None:
        s = MeshSettings.from_quality(MeshQuality.HIGH)
        assert s.linear_deflection == 0.001
        assert s.angular_deflection == 0.1
        assert s.quality == MeshQuality.HIGH

    def test_to_dict(self) -> None:
        s = MeshSettings.from_quality(MeshQuality.MEDIUM)
        d = s.to_dict()
        assert d["quality"] == "MEDIUM"
        assert d["linearDeflection"] == 0.002


class TestPrecisionSettings:
    def test_draft(self) -> None:
        s = PrecisionSettings.draft()
        assert s.length_tolerance == 0.001
        assert s.require_manifold is False

    def test_standard(self) -> None:
        s = PrecisionSettings.standard()
        assert s.length_tolerance == 0.0001
        assert s.require_manifold is True

    def test_high(self) -> None:
        s = PrecisionSettings.high()
        assert s.length_tolerance == 0.00001

    def test_ultra(self) -> None:
        s = PrecisionSettings.ultra()
        assert s.length_tolerance == 0.000001

    def test_to_dict(self) -> None:
        s = PrecisionSettings.standard()
        d = s.to_dict()
        assert "lengthTolerance" in d
        assert "mesh" in d


class TestPrecisionValidator:
    def test_validate_length_pass(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_length(0.1, 0.1, name="width")
        assert passed is True
        assert msg == ""

    def test_validate_length_fail(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_length(0.101, 0.1, name="width")
        assert passed is False
        assert "width" in msg

    def test_validate_angle_pass(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_angle(1.57, 1.57, name="angle")
        assert passed is True

    def test_validate_angle_fail(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_angle(1.6, 1.57, name="angle")
        assert passed is False

    def test_validate_volume_pass(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_volume(0.001, 0.001, name="volume")
        assert passed is True

    def test_validate_volume_fail(self) -> None:
        v = PrecisionValidator()
        passed, msg = v.validate_volume(0.002, 0.001, name="volume")
        assert passed is False

    def test_validate_dimensions(self) -> None:
        v = PrecisionValidator()
        results = v.validate_dimensions(
            actual=(0.1, 0.2, 0.3),
            expected=(0.1, 0.2, 0.3),
        )
        assert all(passed for passed, _ in results)

    def test_validate_bbox(self) -> None:
        v = PrecisionValidator()
        results = v.validate_bbox(
            actual_min=(0.0, 0.0, 0.0),
            actual_max=(0.1, 0.2, 0.3),
            expected_min=(0.0, 0.0, 0.0),
            expected_max=(0.1, 0.2, 0.3),
        )
        assert all(passed for passed, _ in results)


class TestCreatePrecisionValidator:
    def test_default(self) -> None:
        v = create_precision_validator()
        assert v.settings.length_tolerance == 0.0001

    def test_high_quality(self) -> None:
        v = create_precision_validator(MeshQuality.HIGH)
        assert v.settings.length_tolerance == 0.00001
