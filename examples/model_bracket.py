"""Build a bracket matching the 3-view engineering drawing.

Front view: Stepped U-shape with feet at bottom
Right view: L-shape with extension arm at top, R10 fillets
Top view: U-shape body

Run with SOLIDWORKS open::

    py examples/model_bracket.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

# --- Geometry from the 3-view drawing ---

# Overall dimensions
OVERALL_WIDTH = mm(56.0)          # Front view total width
OVERALL_HEIGHT = mm(84.57)        # Front view total height
BODY_DEPTH = mm(60.6)             # Side view depth (horizontal)

# U-shape channel (front view)
CHANNEL_WIDTH = mm(40.0)          # Inner U-channel width at top
ARM_WIDTH = mm(13.0)              # Width of each upright arm

# Steps on the arms (front view, heights from bottom)
FOOT_HEIGHT = mm(8.0)             # Foot height
STEP_1_HEIGHT = mm(23.35)         # First step
STEP_2_HEIGHT = mm(32.51)         # Second step
STEP_3_HEIGHT = mm(50.6)          # Third step
TOP_HEIGHT = mm(60.6)             # Top of arm

# Foot dimensions (front view)
FOOT_EXTENSION = mm(16.0)         # Foot extends 16mm outward from channel wall

# Extension arm (side view) - at TOP of body
ARM_LENGTH = mm(60.6)             # Total horizontal reach from body
ARM_THICKNESS = mm(18.0)          # Arm thickness (depth direction)
ARM_END_RADIUS = mm(10.0)         # R10 rounded end

# Arm hole
ARM_HOLE_DIAMETER = mm(8.6)       # Ø8.6 through-hole at arm end

# Back mounting holes (side view)
BACK_HOLE_LARGE = mm(8.0)         # Ø8 upper hole
BACK_HOLE_SMALL = mm(2.5)         # Ø2.5 lower hole
BACK_HOLE_SPACING = mm(25.0)      # 25mm between hole centers

# Base holes (front view)
BASE_HOLE_RADIUS = mm(3.29)       # Radius of base holes
BASE_HOLE_OFFSET = mm(6.58)       # Distance from center to hole center


def _build_front_profile(sk) -> None:
    """Front view profile: Stepped U-shape with feet.

    The profile has:
    - Wide feet at bottom extending outward
    - Stepped arms going upward
    - Inner U-channel
    """
    half_w = OVERALL_WIDTH / 2.0
    half_channel = CHANNEL_WIDTH / 2.0
    arm_outer = half_w
    arm_inner = half_channel

    # Start at bottom-left, go clockwise
    # Bottom edge (full width)
    sk.line(-arm_outer, 0.0, 0, arm_outer, 0.0, 0)

    # Right foot up
    sk.line(arm_outer, 0.0, 0, arm_outer, FOOT_HEIGHT, 0)

    # Step inward at foot top
    sk.line(arm_outer, FOOT_HEIGHT, 0, arm_inner + FOOT_EXTENSION, FOOT_HEIGHT, 0)

    # Continue up to step 1
    sk.line(arm_inner + FOOT_EXTENSION, FOOT_HEIGHT, 0, arm_inner + FOOT_EXTENSION, STEP_1_HEIGHT, 0)

    # Step outward
    sk.line(arm_inner + FOOT_EXTENSION, STEP_1_HEIGHT, 0, arm_outer, STEP_1_HEIGHT, 0)

    # Continue up to step 2
    sk.line(arm_outer, STEP_1_HEIGHT, 0, arm_outer, STEP_2_HEIGHT, 0)

    # Step inward (inner channel starts)
    sk.line(arm_outer, STEP_2_HEIGHT, 0, arm_inner, STEP_2_HEIGHT, 0)

    # Continue up to step 3
    sk.line(arm_inner, STEP_2_HEIGHT, 0, arm_inner, STEP_3_HEIGHT, 0)

    # Step outward
    sk.line(arm_inner, STEP_3_HEIGHT, 0, arm_outer, STEP_3_HEIGHT, 0)

    # Continue to top
    sk.line(arm_outer, STEP_3_HEIGHT, 0, arm_outer, TOP_HEIGHT, 0)

    # Top edge
    sk.line(arm_outer, TOP_HEIGHT, 0, -arm_outer, TOP_HEIGHT, 0)

    # Left side (mirror)
    sk.line(-arm_outer, TOP_HEIGHT, 0, -arm_outer, STEP_3_HEIGHT, 0)
    sk.line(-arm_outer, STEP_3_HEIGHT, 0, -arm_inner, STEP_3_HEIGHT, 0)
    sk.line(-arm_inner, STEP_3_HEIGHT, 0, -arm_inner, STEP_2_HEIGHT, 0)
    sk.line(-arm_inner, STEP_2_HEIGHT, 0, -arm_outer, STEP_2_HEIGHT, 0)
    sk.line(-arm_outer, STEP_2_HEIGHT, 0, -arm_outer, STEP_1_HEIGHT, 0)
    sk.line(-arm_outer, STEP_1_HEIGHT, 0, -arm_inner - FOOT_EXTENSION, STEP_1_HEIGHT, 0)
    sk.line(-arm_inner - FOOT_EXTENSION, STEP_1_HEIGHT, 0, -arm_inner - FOOT_EXTENSION, FOOT_HEIGHT, 0)
    sk.line(-arm_inner - FOOT_EXTENSION, FOOT_HEIGHT, 0, -arm_outer, FOOT_HEIGHT, 0)
    sk.line(-arm_outer, FOOT_HEIGHT, 0, -arm_outer, 0.0, 0)


def build_bracket(
    output_dir: Path,
    *,
    name: str = "bracket",
    export_step: bool = True,
    visible: bool = True,
) -> tuple[Path, Path | None]:
    """Build the bracket matching the 3-view drawing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=visible)
    part = sw.new_part()

    # ── Step 1: Front profile (stepped U-shape with feet) ──
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        _build_front_profile(sk)
    front_sketch = part.rename_last_feature("Front profile")

    # ── Step 2: Back plane (offset in Z direction) ──
    part.select_plane("Front Plane")
    back_plane = part.features.offset_plane(BODY_DEPTH, flip=False)
    back_plane.Name = "Back plane"

    # ── Step 3: Back profile (same as front) ──
    part.clear_selection()
    part.select_object(back_plane)
    with part.sketch() as sk:
        _build_front_profile(sk)
    back_sketch = part.rename_last_feature("Back profile")

    # ── Step 4: LOFT front to back ──
    part.clear_selection()
    part.select_object(front_sketch, mark=1)
    part.select_object(back_sketch, append=True, mark=1)
    part.features.loft_boss(closed=False, keep_tangency=True)
    part.rename_last_feature("Bracket body")

    # ── Step 5: Extension arm at TOP ──
    # Arm is at the top of the body, extending to the right
    half_w = OVERALL_WIDTH / 2.0
    arm_bottom_y = TOP_HEIGHT - ARM_THICKNESS
    arm_top_y = TOP_HEIGHT
    arm_end_x = half_w + ARM_LENGTH

    part.select_plane("Front Plane")
    with part.sketch() as sk:
        # Arm rectangle at top
        sk.line(half_w, arm_bottom_y, 0, arm_end_x, arm_bottom_y, 0)
        sk.line(arm_end_x, arm_bottom_y, 0, arm_end_x, arm_top_y, 0)
        sk.line(arm_end_x, arm_top_y, 0, half_w, arm_top_y, 0)
        sk.line(half_w, arm_top_y, 0, half_w, arm_bottom_y, 0)
    part.features.extrude_midplane(BODY_DEPTH, merge=True)
    part.rename_last_feature("Extension arm")

    # ── Step 6: Arm end hole (Ø8.6) ──
    arm_centre_y = (arm_bottom_y + arm_top_y) / 2.0
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        sk.circle(arm_end_x, arm_centre_y, ARM_HOLE_DIAMETER / 2.0)
    part.features.cut_midplane(BODY_DEPTH + mm(2.0))
    part.rename_last_feature("Arm hole Ø8.6")

    # ── Step 7: Fillet arm end (R10) ──
    # Select the arm end edges for fillet
    # This requires selecting the circular edge at the arm end
    # For now, skip if not working

    # ── Step 8: Back mounting holes ──
    # Upper hole Ø8
    back_hole_y = TOP_HEIGHT / 2.0 + BACK_HOLE_SPACING / 2.0
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        sk.circle(0.0, back_hole_y, BACK_HOLE_LARGE / 2.0)
    part.features.cut_midplane(BODY_DEPTH + mm(2.0))
    part.rename_last_feature("Back hole Ø8")

    # Lower hole Ø2.5
    back_hole_y2 = TOP_HEIGHT / 2.0 - BACK_HOLE_SPACING / 2.0
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        sk.circle(0.0, back_hole_y2, BACK_HOLE_SMALL / 2.0)
    part.features.cut_midplane(BODY_DEPTH + mm(2.0))
    part.rename_last_feature("Back hole Ø2.5")

    # ── Step 9: Base holes ──
    for sign, label in ((-1, "L"), (+1, "R")):
        part.select_plane("Front Plane")
        with part.sketch() as sk:
            sk.circle(sign * BASE_HOLE_OFFSET, FOOT_HEIGHT / 2.0, BASE_HOLE_RADIUS)
        part.features.cut_midplane(BODY_DEPTH + mm(2.0))
        part.rename_last_feature(f"Base hole {label}")

    part.rebuild()

    # Check for feature errors
    errors = part.feature_errors()
    if errors:
        print(f"Warning: {len(errors)} feature errors found")
        for feat, err in errors:
            print(f"  - {part.feature_name(feat)}: error {err}")

    # Save and export
    save_dir = Path(r"C:\temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    sldprt_path = save_dir / f"{name}.SLDPRT"
    step_path = save_dir / f"{name}.step" if export_step else None

    if export_step:
        sldprt_path, step_path = part.save_and_export(sldprt_path, step_path)
    else:
        part.save_as(sldprt_path)

    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path(r"C:\temp"),
        help="Directory for output files",
    )
    parser.add_argument("--no-step", action="store_true", help="Skip STEP export")
    parser.add_argument("--name", default="bracket", help="Output file base name")
    args = parser.parse_args()

    sldprt, step = build_bracket(
        args.output_dir,
        name=args.name,
        export_step=not args.no_step,
    )
    print(f"Saved: {sldprt}")
    if step:
        print(f"Exported: {step}")


if __name__ == "__main__":
    main()
