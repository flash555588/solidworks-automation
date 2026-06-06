"""Unit tests for solidworks_com.units."""

from __future__ import annotations

import math

import pytest

from solidworks_com.units import cm, deg, inch, mm


class TestLengthConversion:
    def test_mm_returns_meters(self) -> None:
        assert mm(1000) == pytest.approx(1.0)
        assert mm(1) == pytest.approx(0.001)
        assert mm(0) == 0

    def test_cm_returns_meters(self) -> None:
        assert cm(100) == pytest.approx(1.0)
        assert cm(1) == pytest.approx(0.01)

    def test_inch_returns_meters(self) -> None:
        assert inch(1) == pytest.approx(0.0254)
        assert inch(0) == 0

    def test_negative_values(self) -> None:
        assert mm(-50) == pytest.approx(-0.05)
        assert cm(-200) == pytest.approx(-2.0)

    def test_inch_known_reference(self) -> None:
        # 1 inch = exactly 25.4 mm
        assert inch(1) == mm(25.4)


class TestAngleConversion:
    def test_deg_zero(self) -> None:
        assert deg(0) == 0

    def test_deg_180(self) -> None:
        assert deg(180) == pytest.approx(math.pi)

    def test_deg_360(self) -> None:
        assert deg(360) == pytest.approx(2 * math.pi)

    def test_deg_90(self) -> None:
        assert deg(90) == pytest.approx(math.pi / 2)
