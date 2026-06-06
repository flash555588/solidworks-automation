"""Generate 3 DXF views for the canonical mounting-plate example.

The DXF files are checked into `examples/mounting_plate_three_views/`
alongside `generate.py` so a reviewer can re-create them with a
single `python generate.py` invocation.

View convention: third-angle projection.

- front.dxf  : 100 (X) x 10 (Z)    at Y = 0    -- 4 corner circles
- top.dxf    : 100 (X) x 60 (Y)    at Z = 0    -- 4 corner circles
- right.dxf  :  60 (Y) x 10 (Z)    at X = 0    -- 4 corner circles

All views place their rectangle so the centre of the body is at
the local origin.  The 4 corner holes are at (+/-40, +/-20) in
world (X, Y) and centred in Z.

This generator writes the files using ezdxf and exits.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf


OUT_DIR = Path(__file__).resolve().parent

LENGTH = 100.0
WIDTH = 60.0
THICKNESS = 10.0
HOLE_DIA = 6.0
HOLE_R = HOLE_DIA / 2
HOLE_OFFSET_X = 40.0
HOLE_OFFSET_Y = 20.0


def _rect_lines(doc, x_min, y_min, x_max, y_max):
    """Append 4 LINE entities forming a closed rectangle."""
    msp = doc.modelspace()
    corners = [(x_min, y_min), (x_max, y_min),
                (x_max, y_max), (x_min, y_max)]
    for i in range(4):
        a = corners[i]
        b = corners[(i + 1) % 4]
        msp.add_line(start=a, end=b)


def _circles(doc, centres):
    msp = doc.modelspace()
    for (cx, cy) in centres:
        msp.add_circle(center=(cx, cy), radius=HOLE_R)


def _hole_centres_world():
    return [
        (-HOLE_OFFSET_X, -HOLE_OFFSET_Y),
        (+HOLE_OFFSET_X, -HOLE_OFFSET_Y),
        (-HOLE_OFFSET_X, +HOLE_OFFSET_Y),
        (+HOLE_OFFSET_X, +HOLE_OFFSET_Y),
    ]


def _write_front():
    doc = ezdxf.new()
    msp = doc.modelspace()
    # Rectangle: 100 (X) x 10 (Z), centred at origin in this view.
    _rect_lines(doc, -LENGTH / 2, -THICKNESS / 2, +LENGTH / 2, +THICKNESS / 2)
    # Circles: each hole's (x, z) = (x_world, z_world) and they are
    # centred in Y.  We project to (x, z).
    for (hx, hy) in _hole_centres_world():
        msp.add_circle(center=(hx, 0.0), radius=HOLE_R)
    out = OUT_DIR / "front.dxf"
    doc.saveas(str(out))
    print(f"wrote {out}")


def _write_top():
    doc = ezdxf.new()
    _rect_lines(doc, -LENGTH / 2, -WIDTH / 2, +LENGTH / 2, +WIDTH / 2)
    for (hx, hy) in _hole_centres_world():
        # Top view: (x, y) plane; we ignore z.
        doc.modelspace().add_circle(center=(hx, hy), radius=HOLE_R)
    out = OUT_DIR / "top.dxf"
    doc.saveas(str(out))
    print(f"wrote {out}")


def _write_right():
    doc = ezdxf.new()
    # Right view rectangle: 60 (Y) x 10 (Z).
    _rect_lines(doc, -WIDTH / 2, -THICKNESS / 2, +WIDTH / 2, +THICKNESS / 2)
    for (hx, hy) in _hole_centres_world():
        # Right view: (y, z) plane, ignore x.
        doc.modelspace().add_circle(center=(hy, 0.0), radius=HOLE_R)
    out = OUT_DIR / "right.dxf"
    doc.saveas(str(out))
    print(f"wrote {out}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_front()
    _write_top()
    _write_right()


if __name__ == "__main__":
    main()
