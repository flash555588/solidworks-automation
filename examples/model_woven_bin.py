"""Build a woven iron trash bin in SOLIDWORKS.

Simplified approach using body + circular cuts.

Run with SOLIDWORKS open::

    py examples/model_woven_bin.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

BODY_HEIGHT = mm(350.0)
RADIUS = mm(180.0)
BOTTOM_THICKNESS = mm(5.0)

# Woven pattern
NUM_VERTICAL = 12
VERTICAL_WIDTH = mm(25.0)


def build_woven_bin(
    output_dir: Path,
    *,
    name: str = "woven_bin",
    export_step: bool = True,
    visible: bool = True,
) -> tuple[Path, Path | None]:
    """Build the woven iron trash bin."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=True)
    part = sw.new_part()

    # Step 1: Create solid cylindrical body
    print('Creating body...')
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(0.0, 0.0, RADIUS)
    part.features.extrude_blind(BODY_HEIGHT)
    part.rename_last_feature("Body")
    part.rebuild()

    # Step 2: Create vertical slots
    print(f'Creating {NUM_VERTICAL} vertical slots...')
    slot_bottom = BOTTOM_THICKNESS + mm(20.0)
    slot_top = BODY_HEIGHT - mm(20.0)
    total_width = NUM_VERTICAL * VERTICAL_WIDTH
    start_x = -total_width / 2

    for i in range(NUM_VERTICAL):
        x = start_x + i * VERTICAL_WIDTH + VERTICAL_WIDTH / 2
        print(f'  Slot {i+1}/{NUM_VERTICAL}...')

        part.select_plane("Front Plane")
        with part.sketch() as sk:
            hw = VERTICAL_WIDTH / 2
            sk.line(x - hw, slot_bottom, 0, x + hw, slot_bottom, 0)
            sk.line(x + hw, slot_bottom, 0, x + hw, slot_top, 0)
            sk.line(x + hw, slot_top, 0, x - hw, slot_top, 0)
            sk.line(x - hw, slot_top, 0, x - hw, slot_bottom, 0)
        part.features.cut_midplane(RADIUS * 3)
        part.rename_last_feature(f"VSlot {i+1}")
        part.rebuild()

    # Save
    save_dir = Path(r"C:\temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    sldprt_path = save_dir / f"{name}.SLDPRT"
    step_path = save_dir / f"{name}.step" if export_step else None

    print('Saving...')
    part.rebuild()
    if export_step:
        sldprt_path, step_path = part.save_and_export(sldprt_path, step_path)
    else:
        part.save_as(sldprt_path)

    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="woven_bin")
    args = parser.parse_args()

    sldprt, step = build_woven_bin(Path(r"C:\temp"), name=args.name)
    print(f"Saved: {sldprt}")
    if step:
        print(f"Exported: {step}")


if __name__ == "__main__":
    main()
