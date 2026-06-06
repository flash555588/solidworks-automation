"""Build a realistic ergonomic wireless mouse with battery compartment and USB receiver slot.

Coordinate system
-----------------
Mouse body sits above Top Plane (XY, Z=0 = sole).

    X  –  mouse length  (+X = button nose, −X = tail)
    Y  –  mouse width   (symmetric about Y=0)
    Z  –  mouse height  (Z=0 = sole, Z>0 = upward)

Loft profiles
-------------
Six YZ-plane ellipses on Right Plane (YZ, normal X) offsets.
On these offset planes: sketch-X = world Y, sketch-Y = world Z.
Each ellipse is bottom-aligned (base at sketch-Y=0 = world Z=0).

Cut strategy — all use cut_midplane
------------------------------------
cut_blind from Top Plane defaults to −Z (AWAY from the body above Z=0).
cut_midplane(d) cuts ±d/2, always reaches a body starting at Z=0.

    Bottom pockets  : cut_midplane(depth * 2)
    Through-cuts    : cut_midplane(mm(200))   (> max body height ~72 mm)

Sketch contours
---------------
Only circle and corner_rectangle are used; both are guaranteed-closed.
Never use manual line+arc combinations — they require explicit Coincident
constraints or select_closed_contours() will find nothing.
Use sk.oblong() for rounded slots instead.

Output:
    - SLDPRT  (native SOLIDWORKS part)
    - STEP    (optional exchange format)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-sections on Right Plane (YZ, normal X) offsets
# Palm peak is near X=0; +X = button nose, −X = tail.
# ---------------------------------------------------------------------------
SECTIONS = [
    #  x_offset    half_width(Y)   half_height(Z)   label
    (mm( 56),      mm(20.0),        mm( 7.0),        "Front tip"),
    (mm( 38),      mm(25.0),        mm(14.0),        "Button centre"),
    (mm( 20),      mm(28.5),        mm(24.0),        "Wheel area"),
    (mm(  0),      mm(30.0),        mm(36.0),        "Palm peak"),
    (mm(-22),      mm(27.5),        mm(29.0),        "Palm rear"),
    (mm(-48),      mm(20.0),        mm(18.0),        "Tail"),
]

# Detail dims
WHEEL_X      = mm(22.0)
WHEEL_R      = mm(7.0)
BUTTON_GAP_W = mm(1.2)
BUTTON_GAP_FRONT = mm(45.0)
BUTTON_GAP_REAR  = mm(5.0)
BATTERY_DIA  = mm(14.5)
BATTERY_LEN  = mm(50.5)
BATTERY_DEPTH = mm(16.0)
BATTERY_CX   = mm(-6.0)
RECEIVER_W   = mm(7.0)
RECEIVER_L   = mm(14.0)
RECEIVER_D   = mm(3.5)
RECEIVER_CX  = mm(-42.0)
BOTTOM_FILLET_R = mm(5.0)


def _make_offset_plane(part, name, x_offset):
    """Create a YZ-parallel plane at x_offset from Right Plane (normal X)."""
    part.clear_selection()
    part.select_plane("Right Plane")
    plane = part.features.offset_plane(abs(x_offset), flip=(x_offset < 0))
    plane.Name = name
    return plane


def build_wireless_mouse(
    output_dir: Path,
    *,
    name="wireless_mouse",
    export_step=True,
    visible=True,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=visible)
    part = sw.new_part()

    # ================================================================
    # Step 1 – Loft body from 6 elliptical cross-sections
    # ================================================================
    sketches = []
    for offset, hw, hh, label in SECTIONS:
        plane = _make_offset_plane(part, f"Plane {label}", offset)
        part.clear_selection()
        part.select_object(plane)
        with part.sketch() as sk:
            # Bottom-aligned ellipse on Right-Plane offset
            # sketch-X = world Y (width), sketch-Y = world Z (height)
            # center=(0, hh), horizontal radius=hw, vertical radius=hh
            sk.ellipse(0.0, hh, hw, hh, 0.0, 2.0 * hh)
        sketch = part.rename_last_feature(f"Profile {label}")
        sketches.append(sketch)

    part.clear_selection()
    for i, sk_feat in enumerate(sketches):
        part.select_object(sk_feat, append=(i > 0), mark=1)
    part.features.loft_boss(closed=False, keep_tangency=True)
    part.rename_last_feature("Mouse body")

    # ================================================================
    # Step 2 – Battery compartment (rectangular pocket, bottom)
    # ================================================================
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = BATTERY_DIA / 2.0
        hl = BATTERY_LEN / 2.0
        sk.corner_rectangle(BATTERY_CX - hl, -hw, BATTERY_CX + hl, hw)
    part.features.cut_midplane(BATTERY_DEPTH * 2)
    part.rename_last_feature("Battery compartment")

    # ================================================================
    # Step 3 – USB receiver slot (bottom, tail)
    # ================================================================
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = RECEIVER_W / 2.0
        hl = RECEIVER_L / 2.0
        sk.corner_rectangle(RECEIVER_CX - hl, -hw, RECEIVER_CX + hl, hw)
    part.features.cut_midplane(RECEIVER_D * 2)
    part.rename_last_feature("Receiver slot")

    # ================================================================
    # Step 4 – Scroll-wheel recess (through cut)
    # ================================================================
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(WHEEL_X, 0.0, WHEEL_R)
    part.features.cut_midplane(mm(80))
    part.rename_last_feature("Wheel recess")

    # ================================================================
    # Step 5 – Left / Right button separation gap
    # ================================================================
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = BUTTON_GAP_W / 2.0
        sk.corner_rectangle(BUTTON_GAP_FRONT, -hw, BUTTON_GAP_REAR, hw)
    part.features.cut_midplane(mm(80))
    part.rename_last_feature("Button gap")

    # ================================================================
    # Step 6 – Bottom fillet
    # ================================================================
    try:
        part.select_edge_by_ray(
            origin=(0.0, 0.0, mm(2.0)),
            direction=(0.0, 0.0, -1.0),
            radius=mm(1.0),
        )
        part.features.fillet_selected(BOTTOM_FILLET_R)
        part.rename_last_feature("Bottom fillet")
    except Exception as e:
        logger.debug("Bottom fillet skipped: %s", e)

    # ================================================================
    # Rebuild and save
    # ================================================================
    part.rebuild()
    errors = part.feature_errors()
    if errors:
        print(f"Warning: {len(errors)} feature error(s)")
        for feat, err in errors:
            print(f"  - {part.feature_name(feat)}: error {err}")

    sldprt = output_dir / f"{name}.SLDPRT"
    step = (output_dir / f"{name}.step") if export_step else None
    if export_step:
        sldprt, step = part.save_and_export(sldprt, step)
    else:
        part.save_as(sldprt)
    return sldprt, step


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=Path("output"))
    p.add_argument("--name", default="wireless_mouse")
    p.add_argument("--no-step", action="store_true")
    p.add_argument("--hidden", action="store_true")
    args = p.parse_args()

    sldprt, step = build_wireless_mouse(
        args.output_dir,
        name=args.name,
        export_step=not args.no_step,
        visible=not args.hidden,
    )
    print(f"Saved: {sldprt}")
    if step:
        print(f"STEP : {step}")


if __name__ == "__main__":
    main()
