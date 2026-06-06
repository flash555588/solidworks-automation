"""DXF three-view -> CAD-IR v1 reader (MVP).

The MVP supports a deliberately narrow slice of DXF:

- Three DXF files, named after the view convention:
  - the *front* view (looks in the -Y direction, in the XZ plane)
  - the *top* view   (looks in the -Z direction, in the XY plane)
  - the *right* view (looks in the -X direction, in the YZ plane)
- Each view contains only LINE and CIRCLE entities.
- The first view's outer outline is taken to be the base body
  rectangle; subsequent CIRCLE entities are taken to be through-
  holes, in **order**.  The first CIRCLE in front pairs with the
  first CIRCLE in top and the first CIRCLE in right, and so on.
- The convention is third-angle projection (ISO).  This is the most
  common in mechanical engineering practice.

Anything outside this slice raises `DXFReaderError` with a clear
message.  We do not attempt auto-detection of view convention, units,
or layer structure in v0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.entities import DXFGraphic


SCHEMA = "cad_ir.v0"
TOL = 1e-6


class DXFReaderError(Exception):
    pass


def _read_view(path: Path):
    """Return (lines, circles) for one DXF view, with absolute
    coordinates.
    """
    try:
        doc = ezdxf.readfile(str(path))
    except ezdxf.DXFStructureError as exc:
        raise DXFReaderError(f"failed to read DXF {path}: {exc}") from exc
    msp = doc.modelspace()
    lines = []
    circles = []
    for e in msp:
        if e.dxftype() == "LINE":
            start = e.dxf.start
            end = e.dxf.end
            lines.append(((start.x, start.y), (end.x, end.y)))
        elif e.dxftype() == "CIRCLE":
            center = e.dxf.center
            circles.append((center.x, center.y, e.dxf.radius))
        else:
            raise DXFReaderError(
                f"unsupported entity {e.dxftype()!r} in {path.name}; "
                "v0 reader only accepts LINE and CIRCLE"
            )
    return lines, circles


def _rect_from_lines(lines):
    """Return (cx_min, cy_min, cx_max, cy_max) if `lines` form a
    closed rectangle (4 segments meeting at 4 vertices), else raise.
    """
    if len(lines) != 4:
        raise DXFReaderError(
            f"v0 reader expects exactly 4 LINE entities forming a "
            f"rectangle; got {len(lines)}"
        )
    pts = []
    for a, b in lines:
        pts.append(a)
        pts.append(b)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if (x_max - x_min) < TOL or (y_max - y_min) < TOL:
        raise DXFReaderError(f"rectangle is degenerate: {x_min, x_max, y_min, y_max}")
    return x_min, y_min, x_max, y_max


def _pair_circles_by_order(front_circles, top_circles, right_circles):
    """Pair the i-th circle from each view into one through-hole.

    The number of circles must match across the three views; if not,
    we raise.  This is the v0 simplification: callers who draw a
    DXF in three views by hand must draw the same number of circles
    in each view, in the same order.
    """
    n_front = len(front_circles)
    n_top = len(top_circles)
    n_right = len(right_circles)
    if n_front == n_top == n_right:
        return list(zip(front_circles, top_circles, right_circles))
    raise DXFReaderError(
        f"v0 reader requires the same number of CIRCLE entities in "
        f"all three views (ordered pairing); got front={n_front}, "
        f"top={n_top}, right={n_right}"
    )


def read_three_views(front_path, top_path, right_path):
    """Read 3 DXFs and produce a CAD-IR dict.

    Conventions (third-angle projection):

    - The front view's x-axis aligns with the world x-axis; its
      y-axis aligns with the world z-axis.  Each front view
      rectangle (x, y) translates to (x_min..x_max, z_min..z_max).
    - The top view's x-axis aligns with world x; its y-axis aligns
      with world y.  Each top view circle (cx, cy) gives (cx, cy).
    - The right view's x-axis aligns with world y; its y-axis
      aligns with world z.  Each right view circle (cx, cy) gives
      (cy, cz).
    """
    front_lines, front_circles = _read_view(Path(front_path))
    top_lines, top_circles = _read_view(Path(top_path))
    right_lines, right_circles = _read_view(Path(right_path))

    # The base body comes from the front rectangle (X x Z) and the
    # top rectangle (X x Y).
    fx_min, fz_min, fx_max, fz_max = _rect_from_lines(front_lines)
    tx_min, ty_min, tx_max, ty_max = _rect_from_lines(top_lines)
    if abs(fx_min - tx_min) > TOL or abs(fx_max - tx_max) > TOL:
        raise DXFReaderError(
            f"front and top views disagree on x bounds: "
            f"front=[{fx_min}, {fx_max}] top=[{tx_min}, {tx_max}]"
        )
    # The right view's rectangle is for consistency only; the body's
    # Y extent comes from the top view.  We do require right view
    # bounds to match (Y, Z) so we can catch a mis-drawn drawing.
    ry_min, rz_min, ry_max, rz_max = _rect_from_lines(right_lines)
    if abs(ty_min - ry_min) > TOL or abs(ty_max - ry_max) > TOL:
        raise DXFReaderError(
            f"top and right views disagree on y bounds: "
            f"top=[{ty_min}, {ty_max}] right=[{ry_min}, {ry_max}]"
        )
    if abs(fz_min - rz_min) > TOL or abs(fz_max - rz_max) > TOL:
        raise DXFReaderError(
            f"front and right views disagree on z bounds: "
            f"front=[{fz_min}, {fz_max}] right=[{rz_min}, {rz_max}]"
        )

    # The base body, centered at the world origin.
    length_x = fx_max - fx_min
    width_y = ty_max - ty_min
    thickness_z = fz_max - fz_min
    center_x = (fx_min + fx_max) / 2
    center_y = (ty_min + ty_max) / 2

    # Pair the holes (ordered by index) and project to world coords.
    pairs = _pair_circles_by_order(front_circles, top_circles, right_circles)
    holes = []
    for idx, (fc, tc, rc) in enumerate(pairs):
        fx, fz, fr = fc
        tx, ty, tr = tc
        ry, rz, rr = rc
        # Radii must match within tolerance.
        if max(abs(fr - tr), abs(fr - rr)) > TOL:
            raise DXFReaderError(
                f"hole {idx}: radius mismatch across views: "
                f"front={fr}, top={tr}, right={rr}"
            )
        # Centers must match in the shared axes.
        if abs(fx - tx) > TOL:
            raise DXFReaderError(
                f"hole {idx}: x mismatch front={fx} top={tx}"
            )
        if abs(ty - ry) > TOL:
            raise DXFReaderError(
                f"hole {idx}: y mismatch top={ty} right={ry}"
            )
        if abs(fz - rz) > TOL:
            raise DXFReaderError(
                f"hole {idx}: z mismatch front={fz} right={rz}"
            )
        holes.append({
            "x": tx - center_x,
            "y": ty - center_y,
            "diameter": 2 * fr,
        })

    return _build_ir(length_x, width_y, thickness_z, holes, center_x, center_y)


def _build_ir(length, width, thickness, holes, cx, cy):
    """Translate the geometry into a CAD-IR v1 dict."""
    return {
        "schema": SCHEMA,
        "units": "mm",
        "document": {
            "type": "part",
            "name": "imported_plate",
        },
        "coordinate_system": {
            "origin": "part_center",
            "up_axis": "Z",
            "front_axis": "Y",
        },
        "parameters": {
            "plate_length": float(length),
            "plate_width": float(width),
            "plate_thickness": float(thickness),
            **{f"hole_{i}_x": float(h["x"]) for i, h in enumerate(holes)},
            **{f"hole_{i}_y": float(h["y"]) for i, h in enumerate(holes)},
            **{f"hole_{i}_diameter": float(h["diameter"]) for i, h in enumerate(holes)},
        },
        "features": [
            {
                "id": "base",
                "type": "extrude_add",
                "sketch": {
                    "plane": "XY",
                    "entities": [{
                        "type": "center_rectangle",
                        "center": [0, 0],
                        "size": ["plate_length", "plate_width"],
                    }],
                },
                "depth": "plate_thickness",
                "direction": "+Z",
            },
            *({
                "id": f"hole_{i}",
                "type": "hole_through",
                "target": "base",
                "diameter": f"hole_{i}_diameter",
                "axis": "Z",
                "position": [f"hole_{i}_x", f"hole_{i}_y"],
            } for i in range(len(holes))),
        ],
        "acceptance": {
            "bbox": [float(length), float(width), float(thickness)],
            "must_have": ["single_solid"] + [f"{len(holes)}_through_holes"],
            "tolerance_mm": 0.05,
        },
    }


def main(argv):
    if len(argv) < 4:
        print("Usage: dxf_to_ir.py <front.dxf> <top.dxf> <right.dxf> [-o output.json]",
              file=sys.stderr)
        return 2
    out = None
    args = list(argv)
    if "-o" in args:
        i = args.index("-o")
        if i + 1 >= len(args):
            print("dxf_to_ir.py: -o requires a path", file=sys.stderr)
            return 2
        out = Path(args[i + 1])
        # Drop the -o and its argument; the first 3 remaining args
        # are the DXF paths.
        del args[i]
        del args[i]
    try:
        ir = read_three_views(args[1], args[2], args[3])
    except DXFReaderError as exc:
        print(f"dxf_to_ir: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(ir, indent=2) + "\n"
    if out is not None:
        out.write_text(rendered, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0
