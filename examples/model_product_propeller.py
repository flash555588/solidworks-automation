"""Create a manufacturable twisted propeller in SOLIDWORKS.

The propeller is built from a central hub plus a single ``master blade`` lofted
along airfoil station profiles. For ``blade_count > 1`` we build that many
independent loft bodies (one per azimuth) rather than a circular pattern; the
mark=4-based circular pattern is fragile under the new physics-driven
geometry (the loft body no longer intersects the hub axis, which is what
``FeatureCircularPattern4`` needs).

The blade geometry is generated from a small set of physics-driven shape
parameters on ``PropellerSpec``:

* chord varies from ``hub_chord`` to ``tip_chord`` via a roughly-elliptical
  blend (no knife-edge at the tip);
* pitch follows ``beta(r) = atan(design_pitch / (2 * pi * r))`` — the
  constant-angle-of-attack rule for geometric pitch;
* thickness tapers from ``hub_thickness_ratio`` to ``tip_thickness_ratio``
  (root thicker, tip thinner);
* the blade is sampled at ``n_stations`` radial positions.

Run::

    python examples/model_product_propeller.py --blades 3
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, deg, mm


@dataclass(frozen=True)
class PropellerSpec:
    """Geometry parameters for a propeller.

    Chord, pitch, and thickness are no longer hard-coded per station;
    instead a few physics-driven shape parameters drive a smooth
    distribution along the radius:

    * ``hub_chord`` / ``tip_chord`` set the chord at the hub and at the
      tip; values in between follow a smooth ``(1 - t**1.5)`` /
      ``t**1.5`` blend (roughly elliptical, no knife-edge at the tip).
    * ``design_pitch`` is the prop's geometric pitch (P); the local
      pitch angle is ``beta(r) = atan(P / (2*pi*r))`` (constant
      angle-of-attack, not linear interpolation between root and tip).
    * ``hub_thickness_ratio`` is the NACA relative thickness at the root;
      it tapers linearly to ``tip_thickness_ratio`` at the tip.
    * ``n_stations`` controls the number of radial control points; the
      loft is much smoother with >= 10.
    """

    blade_count: int = 2
    diameter: float = mm(127.0)
    hub_radius: float = mm(15.0)
    hub_thickness: float = mm(8.0)  # physical extrusion depth
    bore_radius: float = mm(2.55)
    bolt_circle_radius: float = mm(6.0)
    bolt_hole_radius: float = mm(1.15)
    bolt_count: int = 4
    through_cut_depth: float = mm(24.0)
    # Aerodynamic shape (replaces the old hand-tuned 6-station table):
    design_pitch: float = mm(76.2)  # 3" pitch for a "5x3" prop
    hub_chord: float = mm(22.0)  # chord at the hub edge
    tip_chord: float = mm(4.0)  # finite chord at the tip (NOT 0.45 mm)
    hub_thickness_ratio: float = 0.14  # NACA 14% thick at the root
    tip_thickness_ratio: float = 0.07  # NACA 7% thick at the tip
    n_stations: int = 12  # radial control points along the blade
    name: str = ""

    def __post_init__(self) -> None:
        if self.blade_count < 1:
            raise ValueError(f"blade_count must be >= 1, got {self.blade_count}")
        if self.n_stations < 3:
            raise ValueError(f"n_stations must be >= 3, got {self.n_stations}")
        if self.tip_chord <= 0:
            raise ValueError(f"tip_chord must be > 0, got {self.tip_chord}")
        if self.tip_thickness_ratio >= self.hub_thickness_ratio:
            raise ValueError(
                f"tip_thickness_ratio ({self.tip_thickness_ratio}) must be "
                f"less than hub_thickness_ratio ({self.hub_thickness_ratio}); "
                "real propellers taper thinner toward the tip."
            )
        if not self.name:
            object.__setattr__(
                self,
                "name",
                f"production_5x3_{self.blade_count}_blade_propeller",
            )


@dataclass(frozen=True)
class BladeStation:
    radius: float
    chord: float
    pitch_deg: float
    thickness_ratio: float


def naca_4digit_symmetric_surfaces(
    count: int = 25, thickness: float = 0.12
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return upper and lower NACA 00xx airfoil surfaces from trailing edge to trailing edge."""
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for i in range(count):
        x = 0.5 * (1.0 - math.cos(math.pi * i / (count - 1)))
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(max(x, 0.0))
                - 0.1260 * x
                - 0.3516 * x**2
                + 0.2843 * x**3
                - 0.1036 * x**4
            )
        )
        upper.append((x, yt))
        lower.append((x, -yt))
    return list(reversed(upper)), lower


def _chord_distribution(r: float, spec: PropellerSpec) -> float:
    """Smooth chord at radius ``r`` from ``hub_chord`` to ``tip_chord``.

    Uses a (1 - t**1.5) / t**1.5 blend over the span [hub_radius, r_tip].
    The exponent 1.5 keeps the second derivative near zero, so the
    cubic-spline fit doesn't produce visible concavity in the loft.
    """
    r_tip = spec.diameter / 2.0
    t = (r - spec.hub_radius) / (r_tip - spec.hub_radius)
    t = max(0.0, min(1.0, t))
    return spec.hub_chord * (1.0 - t**1.5) + spec.tip_chord * t**1.5


def _pitch_distribution(r: float, spec: PropellerSpec) -> float:
    """Local pitch angle at radius ``r`` for design pitch ``spec.design_pitch``.

    Real constant-angle-of-attack propellers use the geometric relation
    ``beta(r) = atan(P / (2*pi*r))``. Linear interpolation between root
    and tip (the old design) gives a blade with a varying AoA, which is
    aerodynamically wrong.
    """
    return math.degrees(math.atan(spec.design_pitch / (2.0 * math.pi * r)))


def _thickness_distribution(r: float, spec: PropellerSpec) -> float:
    """Linearly tapered NACA relative thickness from hub to tip."""
    r_tip = spec.diameter / 2.0
    t = (r - spec.hub_radius) / (r_tip - spec.hub_radius)
    t = max(0.0, min(1.0, t))
    return spec.hub_thickness_ratio * (1.0 - t) + spec.tip_thickness_ratio * t


def blade_stations(spec: PropellerSpec) -> list[BladeStation]:
    """Build the radial station table from the spec's physics-driven shape."""
    r_tip = spec.diameter / 2.0
    span = r_tip - spec.hub_radius
    if span <= 0:
        raise ValueError(
            f"diameter ({spec.diameter}) must exceed 2 * hub_radius "
            f"({2 * spec.hub_radius})"
        )
    stations: list[BladeStation] = []
    for index in range(spec.n_stations):
        t = index / (spec.n_stations - 1)
        r = spec.hub_radius + t * span
        stations.append(
            BladeStation(
                radius=r,
                chord=_chord_distribution(r, spec),
                pitch_deg=_pitch_distribution(r, spec),
                thickness_ratio=_thickness_distribution(r, spec),
            )
        )
    return stations


def interpolate_stations(
    stations: list[BladeStation], refine: int
) -> list[BladeStation]:
    """Refine the station table by inserting interpolated sub-stations.

    Rule: for ``refine == k`` every adjacent pair of input stations is
    expanded into ``k`` evenly spaced sub-stations, with all four
    attributes (radius, chord, pitch, thickness) linearly interpolated.
    The original endpoints are kept exactly.
    """
    if refine < 1:
        raise ValueError(f"refine must be >= 1, got {refine}")
    if refine == 1:
        return list(stations)
    out: list[BladeStation] = []
    for a, b in zip(stations, stations[1:]):
        for k in range(refine):
            t = k / refine
            out.append(
                BladeStation(
                    radius=a.radius + (b.radius - a.radius) * t,
                    chord=a.chord + (b.chord - a.chord) * t,
                    pitch_deg=a.pitch_deg + (b.pitch_deg - a.pitch_deg) * t,
                    thickness_ratio=a.thickness_ratio
                    + (b.thickness_ratio - a.thickness_ratio) * t,
                )
            )
    out.append(stations[-1])
    return out


def rotate_xy(x: float, y: float, angle: float) -> tuple[float, float]:
    ca = math.cos(angle)
    sa = math.sin(angle)
    return x * ca - y * sa, x * sa + y * ca


def airfoil_point(
    station: BladeStation, chord_x: float, thickness_z: float, blade_angle: float
) -> tuple[float, float, float]:
    beta = deg(station.pitch_deg)
    chord_coord = (0.5 - chord_x) * station.chord
    airfoil_z = thickness_z * station.chord
    tangent = chord_coord * math.cos(beta) - airfoil_z * math.sin(beta)
    z = chord_coord * math.sin(beta) + airfoil_z * math.cos(beta)
    x, y = rotate_xy(station.radius, tangent, blade_angle)
    return (x, y, z)


def station_profile_curves(
    station: BladeStation,
    blade_angle: float,
    *,
    profile_points: int = 25,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    upper, lower = naca_4digit_symmetric_surfaces(
        count=profile_points, thickness=station.thickness_ratio
    )
    return (
        [airfoil_point(station, x, z, blade_angle) for x, z in upper],
        [airfoil_point(station, x, z, blade_angle) for x, z in lower],
    )


def create_station_plane(part, name: str, offset_x: float) -> Any:
    part.clear_selection()
    part.select_plane("Right Plane")
    plane = part.features.offset_plane(abs(offset_x), flip=offset_x < 0.0)
    plane.Name = name
    return plane


def right_plane_sketch_points(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    return [(y, z, 0.0) for _, y, z in points]


def create_closed_profile_on_plane(
    part,
    plane: Any,
    name: str,
    upper_points: list[tuple[float, float, float]],
    lower_points: list[tuple[float, float, float]],
) -> Any:
    part.clear_selection()
    part.select_object(plane)
    with part.sketch() as sk:
        sk.spline(right_plane_sketch_points(upper_points))
        sk.spline(right_plane_sketch_points(lower_points))
    return part.rename_last_feature(name)


def loft_blade(part, sketches: list[Any], feature_name: str) -> Any:
    part.clear_selection()
    for index, sketch in enumerate(sketches):
        part.select_object(sketch, append=index > 0, mark=1)
    part.features.loft_boss(
        closed=False,
        keep_tangency=False,
        force_non_rational=False,
        tess_tolerance_factor=1.2,
        start_matching_type=0,
        end_matching_type=0,
        merge=True,
    )
    return part.rename_last_feature(feature_name)


def make_hub(part, spec: PropellerSpec) -> None:
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(0.0, 0.0, spec.hub_radius)
    part.features.extrude_midplane(spec.hub_thickness)
    part.rename_last_feature("Hub")


def insert_center_axis(part, name: str = "Hub center axis") -> Any:
    """Insert a reference axis along the hub centre."""
    return part.insert_axis_from_planes("Front Plane", "Right Plane", name=name)


def make_master_blade(
    part,
    spec: PropellerSpec,
    *,
    blade_index: int = 0,
    refine: int = 1,
    profile_points: int = 40,
) -> Any:
    """Build one twisted NACA airfoil blade at azimuth 0."""
    stations = interpolate_stations(blade_stations(spec), refine)
    profiles = [
        station_profile_curves(station, 0.0, profile_points=profile_points)
        for station in stations
    ]
    planes = [
        create_station_plane(part, f"Blade {blade_index + 1} plane {station_index + 1}", station.radius)
        for station_index, station in enumerate(stations)
    ]
    sketches = [
        create_closed_profile_on_plane(
            part,
            planes[station_index],
            f"Blade {blade_index + 1} station {station_index + 1}",
            profile[0],
            profile[1],
        )
        for station_index, profile in enumerate(profiles)
    ]
    return loft_blade(part, sketches, f"Blade {blade_index + 1} airfoil")


def cut_mounting_holes(part, spec: PropellerSpec) -> None:
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(0.0, 0.0, spec.bore_radius)
        for index in range(spec.bolt_count):
            angle = 2.0 * math.pi * index / spec.bolt_count + math.pi / 4.0
            x = spec.bolt_circle_radius * math.cos(angle)
            y = spec.bolt_circle_radius * math.sin(angle)
            sk.circle(x, y, spec.bolt_hole_radius)
    part.features.cut_midplane(spec.through_cut_depth)
    part.rename_last_feature("Shaft and mounting holes")


def add_balance_ring(part, spec: PropellerSpec) -> None:
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(0.0, 0.0, spec.hub_radius * 0.78)
        sk.circle(0.0, 0.0, spec.hub_radius * 0.48)
    part.features.extrude_midplane(mm(1.8), merge=True)
    part.rename_last_feature("Raised balance ring")


def build_propeller(
    output_dir: Path,
    export_step: bool = True,
    visible: bool = True,
    blade_count: int = 2,
    name: str = "",
    *,
    refine: int = 1,
    profile_points: int = 40,
) -> tuple[Path, Path | None]:
    """Build a propeller with ``blade_count`` blades."""
    spec = (
        PropellerSpec(blade_count=blade_count, name=name)
        if name
        else PropellerSpec(blade_count=blade_count)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sw = SolidWorks.connect(visible=visible)
    part = sw.new_part()

    make_hub(part, spec)
    for index in range(spec.blade_count):
        make_master_blade(
            part,
            spec,
            blade_index=index,
            refine=refine,
            profile_points=profile_points,
        )
    add_balance_ring(part, spec)
    cut_mounting_holes(part, spec)
    part.rebuild()

    sldprt_path = output_dir / f"{spec.name}.SLDPRT"
    part.save_as(sldprt_path)
    step_path = None
    if export_step:
        step_path = output_dir / f"{spec.name}.step"
        part.export(step_path)
    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a manufacturable twisted propeller in SOLIDWORKS with any number of blades."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "propeller")
    parser.add_argument("--blades", type=int, default=2, help="Number of blades (>= 1). Default 2.")
    parser.add_argument("--name", type=str, default="", help="Override the output file stem.")
    parser.add_argument("--no-step", action="store_true", help="Only save the native SLDPRT file.")
    parser.add_argument("--hidden", action="store_true", help="Run SOLIDWORKS without making the window visible.")
    parser.add_argument(
        "--refine",
        type=int,
        default=1,
        help="Subdivisions between every pair of base stations (>= 1). Default 1 (no refinement).",
    )
    parser.add_argument(
        "--profile-points",
        type=int,
        default=40,
        help="Chordwise sampling density of each station's NACA airfoil. Default 40.",
    )
    args = parser.parse_args()

    sldprt_path, step_path = build_propeller(
        args.output_dir,
        export_step=not args.no_step,
        visible=not args.hidden,
        blade_count=args.blades,
        name=args.name,
        refine=args.refine,
        profile_points=args.profile_points,
    )
    print(f"Saved: {sldprt_path}")
    if step_path is not None:
        print(f"Exported: {step_path}")


if __name__ == "__main__":
    main()
