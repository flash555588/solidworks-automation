"""Unit tests for solidworks_com.geometry."""

from __future__ import annotations

from solidworks_com.geometry import Point, Vector, flatten_points


class TestPoint:
    def test_construction(self) -> None:
        p = Point(1.0, 2.0, 3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0

    def test_equality(self) -> None:
        assert Point(1, 2, 3) == Point(1, 2, 3)
        assert Point(1, 2, 3) != Point(1, 2, 4)

    def test_default_z_is_zero(self) -> None:
        p = Point(1.0, 2.0)
        assert p.z == 0.0


class TestVector:
    def test_construction(self) -> None:
        v = Vector(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0


class TestFlattenPoints:
    def test_2d_tuples(self) -> None:
        out = flatten_points([(1.0, 2.0), (3.0, 4.0)])
        assert out == [1.0, 2.0, 0.0, 3.0, 4.0, 0.0]

    def test_3d_tuples(self) -> None:
        out = flatten_points([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
        assert out == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

    def test_mixed_points_and_tuples(self) -> None:
        out = flatten_points([Point(1.0, 2.0, 3.0), (4.0, 5.0)])
        assert out == [1.0, 2.0, 3.0, 4.0, 5.0, 0.0]

    def test_empty(self) -> None:
        assert flatten_points([]) == []
