"""Build an aircraft turbine blade in SOLIDWORKS.

Simplified version using extrude instead of loft.

Run with SOLIDWORKS open::

    py examples/model_turbine_blade.py
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

# --- Blade geometry ---
BLADE_HEIGHT = mm(80.0)
CHORD = mm(40.0)
THICKNESS = mm(8.0)
TWIST_ANGLE = 30.0  # degrees

# Root
ROOT_HEIGHT = mm(15.0)
ROOT_WIDTH = mm(50.0)


def build_turbine_blade(
    output_dir: Path,
    *,
    name: str = "turbine_blade",
    export_step: bool = True,
    visible: bool = True,
) -> tuple[Path, Path | None]:
    """Build the turbine blade."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=True)
    part = sw.new_part()

    # Step 1: Create airfoil profile on Front Plane
    print('Creating airfoil profile...')
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        # Simplified airfoil (ellipse-like shape)
        num_points = 24
        points = []
        for i in range(num_points):
            angle = 2 * math.pi * i / num_points
            # Airfoil shape: thicker at front, thinner at back
            x = CHORD / 2 * (1 + math.cos(angle))
            y = THICKNESS / 2 * math.sin(angle)
            # Apply some camber
            y += THICKNESS / 4 * math.sin(angle) ** 2
            points.append((x, y))

        # Draw airfoil as lines
        for i in range(num_points):
            j = (i + 1) % num_points
            sk.line(points[i][0], points[i][1], 0,
                   points[j][0], points[j][1], 0)

    part.rename_last_feature("Airfoil profile")
    part.rebuild()

    # Step 2: Extrude blade
    print('Extruding blade...')
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        # Re-draw same profile for extrusion
        num_points = 24
        points = []
        for i in range(num_points):
            angle = 2 * math.pi * i / num_points
            x = CHORD / 2 * (1 + math.cos(angle))
            y = THICKNESS / 2 * math.sin(angle)
            y += THICKNESS / 4 * math.sin(angle) ** 2
            points.append((x, y))

        for i in range(num_points):
            j = (i + 1) % num_points
            sk.line(points[i][0], points[i][1], 0,
                   points[j][0], points[j][1], 0)

    part.features.extrude_blind(BLADE_HEIGHT)
    part.rename_last_feature("Blade body")
    part.rebuild()

    # Step 3: Create root attachment
    print('Creating root...')
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = ROOT_WIDTH / 2
        sk.line(-hw, -ROOT_HEIGHT, 0, hw, -ROOT_HEIGHT, 0)
        sk.line(hw, -ROOT_HEIGHT, 0, hw, 0, 0)
        sk.line(hw, 0, 0, -hw, 0, 0)
        sk.line(-hw, 0, 0, -hw, -ROOT_HEIGHT, 0)
    part.features.extrude_midplane(CHORD)
    part.rename_last_feature("Root")
    part.rebuild()

    # Save
    save_dir = Path(r"C:\temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    sldprt_path = save_dir / f"{name}.SLDPRT"
    step_path = save_dir / f"{name}.step" if export_step else None

    print('Saving...')
    if export_step:
        sldprt_path, step_path = part.save_and_export(sldprt_path, step_path)
    else:
        part.save_as(sldprt_path)

    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="turbine_blade")
    args = parser.parse_args()

    sldprt, step = build_turbine_blade(Path(r"C:\temp"), name=args.name)
    print(f"Saved: {sldprt}")
    if step:
        print(f"Exported: {step}")


if __name__ == "__main__":
    main()
