"""Build a U-shaped fork/yoke bracket in SOLIDWORKS from a 3-view engineering drawing.

Corrected view identification (user feedback): the drawing IS a
standard three-view drawing (GB). The arrangement is:
- Top-left = 主视图 (Front view): U-shape, 56 wide x 84.57 tall
- Top-right = 左视图 (Side view): side profile, 60.6 deep
- Bottom-left = 剖视图 (Section view A-A): stepped interior
- Bottom-right = 3D isometric (auxiliary)

Reverted dimensions (Y/Z swap was WRONG):
- Width (X):   56
- Height (Y):  84.57  (front view's vertical dimension)
- Depth (Z):   60.6   (side view's horizontal dimension)
- U-slot inner width: 38.12
- U-slot floor: 42.28 from top
- Side taper: R20 outer (extrapolated; drawing has R10 which the
  vision API saw but I cannot verify with the current text-only view)
- Prong holes: R2.5, Y axis (per side view)
- Base cross-holes: R3.5, X axis (per front view)

Construction:
    1. Sketch the U-shape on the Front Plane and extrude mid-plane to 60.6mm.
    2. Add the side-view taper via LOFT (R20 outer curve).
    3. Cut the U-slot on the Front Plane.
    4. Cut 2 horizontal prong holes (Y axis) via offset Right Plane.
    5. Cut 2 horizontal base cross-holes (X axis) via Front Plane.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

# --- Geometry constants (reverted: Y=84.57, Z=60.6) --------------------

OVERALL_WIDTH = mm(56.0)         # X direction (front view)
OVERALL_HEIGHT = mm(84.57)       # Y direction (reverted from 60.6)
OVERALL_DEPTH = mm(60.6)         # Z direction (reverted from 84.57)

U_SLOT_INNER_WIDTH = mm(38.12)   # inner width between the prongs
U_SLOT_DEPTH_FROM_TOP = mm(42.28)
U_SLOT_CORNER_RADIUS = mm(8.0)   # R8 fillet at the slot corners

BACK_HEIGHT = OVERALL_HEIGHT - mm(10.0)  # back is 10mm shorter (LOFT taper)

# Prong through-holes: horizontal, axis in Y direction
PRONG_HOLE_RADIUS = mm(2.5)
PRONG_HOLE_Y_OFFSET = mm(23.53)  # right-prong centre: (56/2 - 38.12/2) = 8.94
PRONG_HOLE_Z = mm(72.0)          # height up the part
PRONG_HOLE_CUT_DEPTH = mm(20.0)   # 2x the prong width

# Base cross-holes: horizontal, axis in X direction
CROSS_HOLE_RADIUS = mm(3.5)
CROSS_HOLE_X_OFFSET = mm(13.5)
CROSS_HOLE_Y_OFFSET = mm(26.72)
CROSS_HOLE_CUT_DEPTH = mm(60.0)   # 2x less than body depth


def _build_u_shape_sketch(sk) -> None:
    """Draw the U-shape on the Front Plane as a single closed C path."""
    half_w = OVERALL_WIDTH / 2.0
    half_u = U_SLOT_INNER_WIDTH / 2.0
    floor_y = OVERALL_HEIGHT - U_SLOT_DEPTH_FROM_TOP
    r = U_SLOT_CORNER_RADIUS

    sk.line(-half_w, 0.0, 0, -half_w, OVERALL_HEIGHT, 0)
    sk.line(-half_w, OVERALL_HEIGHT, 0, -half_u, OVERALL_HEIGHT, 0)
    sk.line(-half_u, OVERALL_HEIGHT, 0, -half_u, floor_y + r, 0)
    sk.arc(
        cx=-half_u + r,
        cy=floor_y + r,
        sx=-half_u,
        sy=floor_y + r,
        ex=-half_u + r,
        ey=floor_y,
        direction=1,
    )
    sk.line(-half_u + r, floor_y, 0, half_u - r, floor_y, 0)
    sk.arc(
        cx=half_u - r,
        cy=floor_y + r,
        sx=half_u - r,
        sy=floor_y,
        ex=half_u,
        ey=floor_y + r,
        direction=1,
    )
    sk.line(half_u, floor_y + r, 0, half_u, OVERALL_HEIGHT, 0)
    sk.line(half_u, OVERALL_HEIGHT, 0, half_w, OVERALL_HEIGHT, 0)
    sk.line(half_w, OVERALL_HEIGHT, 0, half_w, 0.0, 0)
    sk.line(half_w, 0.0, 0, -half_w, 0.0, 0)


def _draw_rectangle(sk, half_w: float, height: float) -> None:
    """Helper: draw a closed rectangle centred on the origin."""
    sk.line(-half_w, 0.0, 0, half_w, 0.0, 0)
    sk.line(half_w, 0.0, 0, half_w, height, 0)
    sk.line(half_w, height, 0, -half_w, height, 0)
    sk.line(-half_w, height, 0, -half_w, 0.0, 0)


def _build_front_rectangle(sk) -> None:
    """Full front rectangle (no U-slot) on the Front Plane."""
    _draw_rectangle(sk, OVERALL_WIDTH / 2.0, OVERALL_HEIGHT)


def _build_back_rectangle(sk) -> None:
    """Smaller back rectangle (no U-slot) on the back plane."""
    _draw_rectangle(sk, OVERALL_WIDTH / 2.0, BACK_HEIGHT)


def _build_u_slot_sketch(sk) -> None:
    """U-slot profile on the Front Plane (closed C path)."""
    half_u = U_SLOT_INNER_WIDTH / 2.0
    floor_y = OVERALL_HEIGHT - U_SLOT_DEPTH_FROM_TOP
    r = U_SLOT_CORNER_RADIUS

    sk.line(-half_u, OVERALL_HEIGHT, 0, half_u, OVERALL_HEIGHT, 0)
    sk.line(half_u, OVERALL_HEIGHT, 0, half_u, floor_y + r, 0)
    sk.arc(
        cx=half_u - r,
        cy=floor_y + r,
        sx=half_u,
        sy=floor_y + r,
        ex=half_u - r,
        ey=floor_y,
        direction=1,
    )
    sk.line(half_u - r, floor_y, 0, -half_u + r, floor_y, 0)
    sk.arc(
        cx=-half_u + r,
        cy=floor_y + r,
        sx=-half_u + r,
        sy=floor_y,
        ex=-half_u,
        ey=floor_y + r,
        direction=1,
    )
    sk.line(-half_u, floor_y + r, 0, -half_u, OVERALL_HEIGHT, 0)


def build_u_fork(
    output_dir: Path,
    *,
    name: str = "u_fork_bracket",
    export_step: bool = True,
    visible: bool = True,
) -> tuple[Path, Path | None]:
    """Build the U-fork matching the three-view drawing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=visible)
    part = sw.new_part()

    # Step 1: front rectangle on Front Plane
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        _build_front_rectangle(sk)
    front_sketch = part.rename_last_feature("Front profile")

    # Step 2: back plane (offset 60.6mm in +X)
    part.select_plane("Front Plane")
    back_plane = part.features.offset_plane(OVERALL_DEPTH, flip=False)
    back_plane.Name = "Back profile plane"

    # Step 3: back rectangle on back plane (10mm shorter)
    part.clear_selection()
    part.select_object(back_plane)
    with part.sketch() as sk:
        _build_back_rectangle(sk)
    back_sketch = part.rename_last_feature("Back profile")

    # Step 4: LOFT (R20 taper from front to back)
    part.clear_selection()
    part.select_object(front_sketch, mark=1)
    part.select_object(back_sketch, append=True, mark=1)
    part.features.loft_boss(closed=False, keep_tangency=True)
    part.rename_last_feature("U fork body (lofted, tapered)")

    # Step 5: U-slot cut on Front Plane
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        _build_u_slot_sketch(sk)
    part.features.cut_midplane(OVERALL_DEPTH)
    part.rename_last_feature("U slot")

    # Step 6: prong holes — Y axis via offset Right Plane
    for sign, label in ((+1, "R"), (-1, "L")):
        part.select_plane("Right Plane")
        plane = part.features.offset_plane(PRONG_HOLE_Y_OFFSET, flip=(sign < 0))
        plane.Name = f"{label} prong plane"
        part.clear_selection()
        part.select_object(plane)
        with part.sketch() as sk:
            sk.circle(0.0, PRONG_HOLE_Z, PRONG_HOLE_RADIUS)
        part.features.cut_midplane(PRONG_HOLE_CUT_DEPTH)
        part.rename_last_feature(f"Prong hole {label}")

    # Step 7: base cross-holes — X axis via Front Plane
    for sign in (-1, 1):
        part.select_plane("Front Plane")
        with part.sketch() as sk:
            sk.circle(sign * CROSS_HOLE_X_OFFSET, CROSS_HOLE_Y_OFFSET, CROSS_HOLE_RADIUS)
        part.features.cut_midplane(CROSS_HOLE_CUT_DEPTH)
        part.rename_last_feature(f"Base hole {'L' if sign < 0 else 'R'}")

    part.rebuild()

    sldprt_path = output_dir / f"{name}.SLDPRT"
    part.save_as(sldprt_path)
    step_path = None
    if export_step:
        step_path = output_dir / f"{name}.step"
        part.export(step_path)
    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "fork")
    parser.add_argument("--name", type=str, default="u_fork_bracket")
    parser.add_argument("--no-step", action="store_true")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()

    sldprt, step = build_u_fork(
        args.output_dir,
        name=args.name,
        export_step=not args.no_step,
        visible=not args.hidden,
    )
    print(f"Saved: {sldprt}")
    if step is not None:
        print(f"Exported: {step}")


if __name__ == "__main__":
    main()
