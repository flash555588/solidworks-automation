"""Wireless mouse assembly — top shell + bottom shell + internal parts.

Product structure (real assembly):

    - mouse_bottom.SLDPRT     — lower shell (battery bay + receiver slot)
    - mouse_top.SLDPRT        — upper shell (wheel opening + button gap)
    - mouse_battery.SLDPRT    — AA cell cylinder
    - mouse_receiver.SLDPRT   — USB nano-receiver block
    - mouse_wheel.SLDPRT      — scroll-wheel cylinder
    - wireless_mouse_asm.SLDASM — assembly

Split strategy
--------------
A horizontal split plane at Z = 12 mm divides the loft body:

    - Bottom shell = Z ∈ [0, 12]  (cut away everything above 12 mm)
    - Top shell    = Z ≥ 12 mm     (cut away everything below 12 mm)

The two halves meet at the same flat face and mate naturally when
inserted at the same origin.

Coordinate system
-----------------
    X  — mouse length  (+X = button nose, −X = tail)
    Y  — mouse width   (symmetric about Y=0)
    Z  — mouse height  (Z=0 = sole, Z>0 = upward)
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
# Dimensions
# ---------------------------------------------------------------------------
SECTIONS = [
    (mm(56), mm(20.0), mm(7.0), "Front tip"),
    (mm(38), mm(25.0), mm(14.0), "Button centre"),
    (mm(20), mm(28.5), mm(24.0), "Wheel area"),
    (mm(0), mm(30.0), mm(36.0), "Palm peak"),
    (mm(-22), mm(27.5), mm(29.0), "Palm rear"),
    (mm(-48), mm(20.0), mm(18.0), "Tail"),
]

SPLIT_Z = mm(12.0)

WHEEL_X = mm(22.0)
WHEEL_R = mm(7.0)

BUTTON_GAP_W = mm(1.2)
BUTTON_GAP_FRONT = mm(45.0)
BUTTON_GAP_REAR = mm(5.0)

BATTERY_DIA = mm(14.5)
BATTERY_LEN = mm(50.5)
BATTERY_DEPTH = mm(16.0)
BATTERY_CX = mm(-6.0)

RECEIVER_W = mm(7.0)
RECEIVER_L = mm(14.0)
RECEIVER_D = mm(3.5)
RECEIVER_CX = mm(-42.0)

BOTTOM_FILLET_R = mm(5.0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _offset_plane(part, x_offset: float, name: str):
    part.clear_selection()
    part.select_plane("Right Plane")
    plane = part.features.offset_plane(abs(x_offset), flip=(x_offset < 0))
    plane.Name = name
    return plane


def _build_loft_body(part) -> None:
    """Create the full loft body from six elliptical profiles."""
    profiles = []
    for x_off, hw, hh, label in SECTIONS:
        plane = _offset_plane(part, x_off, f"Plane {label}")
        part.clear_selection()
        part.select_object(plane)
        with part.sketch() as sk:
            sk.ellipse(0.0, hh, hw, hh, 0.0, 2.0 * hh)
        profiles.append(part.rename_last_feature(f"Profile {label}"))

    part.clear_selection()
    part.select_object(profiles[0], mark=1)
    for p in profiles[1:]:
        part.select_object(p, append=True, mark=1)
    part.features.loft_boss(closed=False, keep_tangency=False)
    part.rename_last_feature("Mouse body")


def _split_plane(part) -> None:
    """Create a large rectangle on a Z=12 mm offset plane for body splitting."""
    part.clear_selection()
    part.select_plane("Top Plane")
    plane = part.features.offset_plane(SPLIT_Z)
    plane.Name = "Split plane"
    part.clear_selection()
    part.select_object(plane)
    with part.sketch() as sk:
        sk.corner_rectangle(mm(-100), mm(-100), mm(100), mm(100))


# ---------------------------------------------------------------------------
# Part builders
# ---------------------------------------------------------------------------

def build_bottom_shell(sw: SolidWorks, output_dir: Path) -> Path:
    """Lower shell: Z ∈ [0, 12 mm] with battery bay and receiver slot."""
    part = sw.new_part()

    # 1. Full body
    _build_loft_body(part)

    # 2. Cut away everything above SPLIT_Z (keep bottom half)
    _split_plane(part)
    part.features.cut_blind(mm(200), reverse=True)
    part.rename_last_feature("Split top off")

    # 3. Battery compartment
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = BATTERY_DIA / 2.0
        hl = BATTERY_LEN / 2.0
        sk.corner_rectangle(BATTERY_CX - hl, -hw, BATTERY_CX + hl, hw)
    part.features.cut_midplane(BATTERY_DEPTH * 2)
    part.rename_last_feature("Battery compartment")

    # 4. Receiver slot
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = RECEIVER_W / 2.0
        hl = RECEIVER_L / 2.0
        sk.corner_rectangle(RECEIVER_CX - hl, -hw, RECEIVER_CX + hl, hw)
    part.features.cut_midplane(RECEIVER_D * 2)
    part.rename_last_feature("Receiver slot")

    # 5. Wheel opening (so the wheel is visible through the bottom shell too)
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(WHEEL_X, 0.0, WHEEL_R)
    part.features.cut_midplane(mm(200))
    part.rename_last_feature("Wheel opening")

    # 6. Bottom fillet
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

    part.rebuild()
    path = output_dir / "mouse_bottom.SLDPRT"
    part.save_as(path)
    return path


def build_top_shell(sw: SolidWorks, output_dir: Path) -> Path:
    """Upper shell: Z ≥ 12 mm with wheel opening and button gap."""
    part = sw.new_part()

    # 1. Full body
    _build_loft_body(part)

    # 2. Cut away everything below SPLIT_Z (keep top half)
    _split_plane(part)
    part.features.cut_blind(mm(200))
    part.rename_last_feature("Split bottom off")

    # 3. Wheel opening
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(WHEEL_X, 0.0, WHEEL_R)
    part.features.cut_midplane(mm(200))
    part.rename_last_feature("Wheel opening")

    # 4. Button gap
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        hw = BUTTON_GAP_W / 2.0
        sk.corner_rectangle(BUTTON_GAP_REAR, -hw, BUTTON_GAP_FRONT, hw)
    part.features.cut_midplane(mm(200))
    part.rename_last_feature("Button gap")

    part.rebuild()
    path = output_dir / "mouse_top.SLDPRT"
    part.save_as(path)
    return path


def build_battery(sw: SolidWorks, output_dir: Path) -> Path:
    """AA battery cylinder (axis along X)."""
    part = sw.new_part()
    part.select_plane("Right Plane")
    with part.sketch() as sk:
        sk.circle(0.0, BATTERY_DIA / 2.0, BATTERY_DIA / 2.0)
    part.features.extrude_blind(BATTERY_LEN, reverse=True)
    part.rename_last_feature("Battery body")
    part.rebuild()
    path = output_dir / "mouse_battery.SLDPRT"
    part.save_as(path)
    return path


def build_receiver(sw: SolidWorks, output_dir: Path) -> Path:
    """USB nano-receiver block (axis along X)."""
    part = sw.new_part()
    part.select_plane("Right Plane")
    with part.sketch() as sk:
        hw = RECEIVER_W / 2.0
        sk.corner_rectangle(-hw, 0.0, hw, RECEIVER_D)
    part.features.extrude_blind(RECEIVER_L, reverse=True)
    part.rename_last_feature("Receiver body")
    part.rebuild()
    path = output_dir / "mouse_receiver.SLDPRT"
    part.save_as(path)
    return path


def build_wheel(sw: SolidWorks, output_dir: Path) -> Path:
    """Scroll-wheel cylinder (axis along Y)."""
    part = sw.new_part()
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        sk.circle(WHEEL_X, WHEEL_R, WHEEL_R)
    part.features.extrude_blind(mm(25.0), reverse=True)
    part.rename_last_feature("Wheel body")
    part.rebuild()
    path = output_dir / "mouse_wheel.SLDPRT"
    part.save_as(path)
    return path


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_assembly(
    sw: SolidWorks,
    output_dir: Path,
    components: list[tuple[Path, float, float, float]],
) -> Path:
    asm = sw.new_assembly()
    for path, x, y, z in components:
        asm.add_component(path, x=x, y=y, z=z)
    asm.rebuild()
    path = output_dir / "wireless_mouse_asm.SLDASM"
    asm.save_as(path)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=Path("output"))
    p.add_argument("--hidden", action="store_true")
    args = p.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    visible = not args.hidden

    sw = SolidWorks.connect(visible=visible)

    print("Building bottom shell...")
    bottom_path = build_bottom_shell(sw, output_dir)
    print(f"  -> {bottom_path}")

    print("Building top shell...")
    top_path = build_top_shell(sw, output_dir)
    print(f"  -> {top_path}")

    print("Building battery...")
    battery_path = build_battery(sw, output_dir)
    print(f"  -> {battery_path}")

    print("Building receiver...")
    receiver_path = build_receiver(sw, output_dir)
    print(f"  -> {receiver_path}")

    print("Building wheel...")
    wheel_path = build_wheel(sw, output_dir)
    print(f"  -> {wheel_path}")

    print("Building assembly...")
    components = [
        (bottom_path, 0.0, 0.0, 0.0),
        (top_path, 0.0, 0.0, 0.0),
        (battery_path, mm(-31.25), 0.0, 0.0),
        (receiver_path, mm(-49.0), 0.0, 0.0),
        (wheel_path, 0.0, mm(-12.5), 0.0),
    ]
    asm_path = build_assembly(sw, output_dir, components)
    print(f"  -> {asm_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
