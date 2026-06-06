"""Build a simple wire mesh trash bin.

Run with SOLIDWORKS open::

    py examples/model_wire_bin.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

BODY_HEIGHT = mm(300.0)
BOTTOM_RADIUS = mm(150.0)
NUM_SLOTS = 6


def build_wire_bin(
    output_dir: Path,
    *,
    name: str = "wire_bin",
    export_step: bool = True,
    visible: bool = True,
) -> tuple[Path, Path | None]:
    """Build the wire mesh trash bin."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sw = SolidWorks.connect(visible=True)
    part = sw.new_part()

    # Step 1: Create solid cylindrical body
    print('Creating body...')
    part.select_plane("Top Plane")
    with part.sketch() as sk:
        sk.circle(0.0, 0.0, BOTTOM_RADIUS)
    part.features.extrude_blind(BODY_HEIGHT)
    part.rename_last_feature("Body")

    # Step 2: Create cut slots
    slot_width = mm(20.0)
    slot_bottom = mm(13.0)
    slot_top = BODY_HEIGHT - mm(20.0)

    for i in range(NUM_SLOTS):
        print(f'Creating slot {i+1}/{NUM_SLOTS}...')
        part.select_plane("Front Plane")
        with part.sketch() as sk:
            x = (i - NUM_SLOTS/2 + 0.5) * (slot_width + mm(5.0))
            sk.line(x - slot_width/2, slot_bottom, 0, x + slot_width/2, slot_bottom, 0)
            sk.line(x + slot_width/2, slot_bottom, 0, x + slot_width/2, slot_top, 0)
            sk.line(x + slot_width/2, slot_top, 0, x - slot_width/2, slot_top, 0)
            sk.line(x - slot_width/2, slot_top, 0, x - slot_width/2, slot_bottom, 0)
        part.features.cut_blind(BODY_HEIGHT)
        part.rename_last_feature(f"Slot {i+1}")

    # Rebuild before saving
    print('Rebuilding...')
    part.rebuild()

    # Save
    save_dir = Path(r"C:\temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    sldprt_path = save_dir / f"{name}.SLDPRT"
    step_path = save_dir / f"{name}.step" if export_step else None

    print('Saving...')
    try:
        if export_step:
            sldprt_path, step_path = part.save_and_export(sldprt_path, step_path)
        else:
            part.save_as(sldprt_path)
    except Exception as e:
        print(f'First save failed: {e}')
        print('Rebuilding and retrying...')
        part.rebuild()
        if export_step:
            sldprt_path, step_path = part.save_and_export(sldprt_path, step_path)
        else:
            part.save_as(sldprt_path)

    return sldprt_path, step_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="wire_bin")
    args = parser.parse_args()

    sldprt, step = build_wire_bin(Path(r"C:\temp"), name=args.name)
    print(f"Saved: {sldprt}")
    if step:
        print(f"Exported: {step}")


if __name__ == "__main__":
    main()
