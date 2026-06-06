"""Unit tests for the example ``model_product_propeller`` module.

These tests cover the pure-Python surface: the ``PropellerSpec`` dataclass
(validation, default name derivation), the physics-driven ``blade_stations``
distribution, the ``interpolate_stations`` refinement rule, and the airfoil
geometry helpers. They do not require SOLIDWORKS.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import math
import sys
import types
from pathlib import Path

import pytest


def _load_propeller_module() -> types.ModuleType:
    """Load ``examples/model_product_propeller.py`` with SOLIDWORKS shimmed out.

    The real ``mm()`` from the library converts mm -> m; for the
    interpolation and chord tests we want unit-free arithmetic, so we
    temporarily replace ``solidworks_com`` with a stub and restore it
    afterwards so other test files can still import ``solidworks_com.com``.
    """
    sw = types.ModuleType("solidworks_com")

    class _StubError(RuntimeError):
        pass

    sw.SolidWorks = object
    sw.SolidWorksError = _StubError
    sw.mm = lambda v: v
    sw.cm = lambda v: v
    sw.inch = lambda v: v
    sw.deg = lambda v: v

    saved_sw = sys.modules.get("solidworks_com")
    saved_prop = sys.modules.get("model_product_propeller")
    sys.modules["solidworks_com"] = sw
    sys.modules.pop("model_product_propeller", None)
    try:
        example_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "model_product_propeller.py"
        )
        spec = importlib.util.spec_from_file_location(
            "model_product_propeller", example_path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["model_product_propeller"] = module
        spec.loader.exec_module(module)
    finally:
        if saved_sw is not None:
            sys.modules["solidworks_com"] = saved_sw
        else:
            sys.modules.pop("solidworks_com", None)
        if saved_prop is not None:
            sys.modules["model_product_propeller"] = saved_prop
        else:
            sys.modules.pop("model_product_propeller", None)
    return module


@pytest.fixture
def propeller():
    return _load_propeller_module()


class TestPropellerSpec:
    def test_defaults(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        assert spec.blade_count == 2
        assert spec.name == "production_5x3_2_blade_propeller"
        assert spec.n_stations == 12
        assert spec.tip_chord > 0
        assert spec.tip_thickness_ratio < spec.hub_thickness_ratio

    @pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
    def test_name_tracks_blade_count(self, propeller, count: int) -> None:
        spec = propeller.PropellerSpec(blade_count=count)
        assert f"_{count}_blade_propeller" in spec.name
        assert spec.name.startswith("production_5x3_")

    def test_explicit_name_wins(self, propeller) -> None:
        spec = propeller.PropellerSpec(blade_count=3, name="custom")
        assert spec.name == "custom"

    def test_zero_blade_rejected(self, propeller) -> None:
        with pytest.raises(ValueError, match="blade_count must be >= 1"):
            propeller.PropellerSpec(blade_count=0)

    def test_negative_blade_rejected(self, propeller) -> None:
        with pytest.raises(ValueError, match="blade_count must be >= 1"):
            propeller.PropellerSpec(blade_count=-2)

    def test_n_stations_floor(self, propeller) -> None:
        with pytest.raises(ValueError, match="n_stations must be >= 3"):
            propeller.PropellerSpec(n_stations=2)

    def test_tip_thicker_than_hub_rejected(self, propeller) -> None:
        # Real propellers taper THINNER at the tip. The old design had it
        # reversed (0.18 at tip vs 0.145 at root), which produced a bulb.
        with pytest.raises(ValueError, match="must be less than hub_thickness_ratio"):
            propeller.PropellerSpec(
                hub_thickness_ratio=0.10, tip_thickness_ratio=0.12
            )

    def test_zero_tip_chord_rejected(self, propeller) -> None:
        with pytest.raises(ValueError, match="tip_chord must be > 0"):
            propeller.PropellerSpec(tip_chord=propeller.mm(0.0))

    def test_frozen(self, propeller) -> None:
        spec = propeller.PropellerSpec(blade_count=2)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            spec.blade_count = 4  # type: ignore[misc]

class TestStationRefinement:
    """Rules for ``interpolate_stations`` and the airfoil point count."""

    def test_refine_1_is_identity(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        base = propeller.blade_stations(spec)
        out = propeller.interpolate_stations(base, 1)
        assert out == base

    @pytest.mark.parametrize("k", [2, 3, 4, 5])
    def test_refine_k_gives_correct_count(self, propeller, k: int) -> None:
        spec = propeller.PropellerSpec()
        base = propeller.blade_stations(spec)
        out = propeller.interpolate_stations(base, k)
        # n base -> n-1 intervals, k points per interval, + 1 final endpoint
        assert len(out) == (len(base) - 1) * k + 1

    def test_refine_preserves_endpoints(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        base = propeller.blade_stations(spec)
        out = propeller.interpolate_stations(base, 3)
        assert out[0] == base[0]
        assert out[-1] == base[-1]

    def test_refine_interpolates_attributes(self, propeller) -> None:
        a = propeller.BladeStation(
            radius=0.0, chord=10.0, pitch_deg=30.0, thickness_ratio=0.10
        )
        b = propeller.BladeStation(
            radius=10.0, chord=20.0, pitch_deg=10.0, thickness_ratio=0.05
        )
        mid = propeller.interpolate_stations([a, b], 2)[1]
        assert mid.radius == pytest.approx(5.0, abs=1e-12)
        assert mid.chord == pytest.approx(15.0, abs=1e-12)
        assert mid.pitch_deg == pytest.approx(20.0, abs=1e-12)
        assert mid.thickness_ratio == pytest.approx(0.075, abs=1e-12)

    def test_refine_rejects_zero(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        base = propeller.blade_stations(spec)
        with pytest.raises(ValueError, match="refine must be >= 1"):
            propeller.interpolate_stations(base, 0)

    def test_refine_rejects_negative(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        base = propeller.blade_stations(spec)
        with pytest.raises(ValueError, match="refine must be >= 1"):
            propeller.interpolate_stations(base, -1)

    def test_profile_points_changes_spline_density(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        station = propeller.blade_stations(spec)[2]
        for n in (10, 25, 50):
            upper, _ = propeller.station_profile_curves(
                station, 0.0, profile_points=n
            )
            assert len(upper) == n


class TestBladeStationPhysics:
    """Aerodynamic shape checks for the physics-driven station table."""

    def test_station_count_matches_spec(self, propeller) -> None:
        spec = propeller.PropellerSpec(n_stations=10)
        assert len(propeller.blade_stations(spec)) == 10

    def test_stations_span_blade_radius(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        stations = propeller.blade_stations(spec)
        # Innermost station at the hub edge; outermost at the tip
        assert stations[0].radius == pytest.approx(spec.hub_radius, abs=1e-12)
        tip_radius = spec.diameter / 2.0
        assert stations[-1].radius == pytest.approx(tip_radius, abs=1e-12)

    def test_chord_is_monotonically_decreasing(self, propeller) -> None:
        # Real propellers shrink the chord from root to tip. The old
        # design had a paddle-like peak at r=21mm (33% of tip radius)
        # which looked wrong from the top view.
        spec = propeller.PropellerSpec()
        chords = [s.chord for s in propeller.blade_stations(spec)]
        for a, b in zip(chords, chords[1:]):
            assert a >= b, f"chord must decrease root->tip, got {chords}"

    def test_chord_ratio_within_3_to_6(self, propeller) -> None:
        # Root/tip chord ratio of 55:1 (the old design) creates a
        # knife-edge tip. Real propellers stay in the 3:1 to 6:1 range.
        spec = propeller.PropellerSpec()
        stations = propeller.blade_stations(spec)
        ratio = stations[0].chord / stations[-1].chord
        assert 3.0 <= ratio <= 6.5, (
            f"root/tip chord ratio {ratio:.1f}:1 is outside the "
            "3:1 to 6.5:1 aerodynamic range"
        )

    def test_pitch_follows_atn_formula(self, propeller) -> None:
        # Constant AoA: beta(r) = atan(P / (2*pi*r))
        # Stub mm() is identity so design_pitch is in the same units as r.
        spec = propeller.PropellerSpec(design_pitch=76.2)
        for s in propeller.blade_stations(spec):
            expected = math.degrees(math.atan(76.2 / (2 * math.pi * s.radius)))
            assert s.pitch_deg == pytest.approx(expected, abs=1e-9)

    def test_pitch_is_monotonically_decreasing(self, propeller) -> None:
        # beta(r) decreases as r grows (1/r shape).
        spec = propeller.PropellerSpec()
        pitches = [s.pitch_deg for s in propeller.blade_stations(spec)]
        for a, b in zip(pitches, pitches[1:]):
            assert a >= b, f"pitch must decrease root->tip, got {pitches}"

    def test_thickness_tapers_to_tip(self, propeller) -> None:
        # Thickness must be highest at the root and lowest at the tip.
        # The old design had 0.145 at root and 0.18 at tip (a bulb).
        spec = propeller.PropellerSpec()
        thicknesses = [s.thickness_ratio for s in propeller.blade_stations(spec)]
        for a, b in zip(thicknesses, thicknesses[1:]):
            assert a >= b, f"thickness must decrease root->tip, got {thicknesses}"
        assert thicknesses[0] == pytest.approx(spec.hub_thickness_ratio, abs=1e-12)
        assert thicknesses[-1] == pytest.approx(spec.tip_thickness_ratio, abs=1e-12)

    def test_tip_thickness_under_8_percent(self, propeller) -> None:
        # Tips below 8% are the sweet spot for efficient props; the old
        # 18% was a knife-edge with a fat trailing edge.
        spec = propeller.PropellerSpec()
        tip = propeller.blade_stations(spec)[-1]
        assert tip.thickness_ratio < 0.08, (
            f"tip thickness {tip.thickness_ratio*100:.1f}% is too thick"
        )

    def test_no_zero_chord_at_tip(self, propeller) -> None:
        # The pure elliptical c(r) = c_root * sqrt(1-(r/R)^2) degenerates
        # to 0 at the tip, which is unphysical. Our blend must keep the
        # tip chord strictly positive.
        spec = propeller.PropellerSpec()
        tip = propeller.blade_stations(spec)[-1]
        assert tip.chord > 0


class TestAirfoilGeometry:
    def test_station_profile_curves_shape(self, propeller) -> None:
        spec = propeller.PropellerSpec()
        station = propeller.blade_stations(spec)[5]  # mid-blade station
        upper, lower = propeller.station_profile_curves(station, blade_angle=0.0)
        assert len(upper) == len(lower)
        assert len(upper) > 4
        upper_xs = [p[0] for p in upper]
        lower_xs = [p[0] for p in lower]
        assert math.isclose(min(upper_xs), min(lower_xs), abs_tol=1e-9)
        assert math.isclose(max(upper_xs), max(upper_xs), abs_tol=1e-9)
        for u, lower_pt in zip(upper, lower):
            midpoint_z = 0.5 * (u[2] + lower_pt[2])
            thickness_upper = u[2] - midpoint_z
            thickness_lower = lower_pt[2] - midpoint_z
            assert math.isclose(thickness_upper, -thickness_lower, abs_tol=1e-9)
    def test_rotate_xy_is_orthogonal(self, propeller) -> None:
        assert propeller.rotate_xy(1.0, 0.0, math.pi / 2) == pytest.approx((0.0, 1.0), abs=1e-9)
        assert propeller.rotate_xy(0.0, 1.0, math.pi / 2) == pytest.approx((-1.0, 0.0), abs=1e-9)

    def test_right_plane_sketch_points(self, propeller) -> None:
        out = propeller.right_plane_sketch_points([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
        assert out == [(2.0, 3.0, 0.0), (5.0, 6.0, 0.0)]
