"""Reusable CAD-IR primitives for bicycle-class parts.

These factory functions return ready-to-insert :class:`CADFeature`
objects that follow the v0 schema and integrate with the
existing ``sw_compile`` / ``cad_ir_to_sw`` toolchain.  They are
*parameterised*: every numeric value is a string reference to a
parameter on the :class:`CADIR` document so that callers can
adjust dimensions without editing the primitives.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from .schema import CADFeature, CADIR


# ---------- Wheels ----------

def wheel_pair(
    front_axle: Tuple[str, str],
    rear_axle: Tuple[str, str],
    radius: str = "wheel_radius",
    thickness: str = "wheel_thickness",
    inner_radius: str = "wheel_inner_radius",
) -> list:
    """Return the four features for a front/rear wheel (outer + inner cut)."""
    fx, _fz = front_axle
    rx, _rz = rear_axle
    return [
        CADFeature(
            id="front_wheel_outer", type="extrude_add",
            parameters={
                "sketch": {
                    "plane": "XZ",
                    "entities": [
                        {"type": "circle", "center": [fx, 0],
                         "diameter": radius},
                    ],
                },
                "depth": thickness,
                "direction": "+Y",
            },
        ),
        CADFeature(
            id="front_wheel_inner", type="extrude_cut",
            parameters={
                "target": "front_wheel_outer",
                "sketch": {
                    "plane": "XZ",
                    "entities": [
                        {"type": "circle", "center": [fx, 0],
                         "diameter": inner_radius},
                    ],
                },
                "depth": thickness,
                "direction": "+Y",
            },
        ),
        CADFeature(
            id="rear_wheel_outer", type="extrude_add",
            parameters={
                "sketch": {
                    "plane": "XZ",
                    "entities": [
                        {"type": "circle", "center": [rx, 0],
                         "diameter": radius},
                    ],
                },
                "depth": thickness,
                "direction": "+Y",
            },
        ),
        CADFeature(
            id="rear_wheel_inner", type="extrude_cut",
            parameters={
                "target": "rear_wheel_outer",
                "sketch": {
                    "plane": "XZ",
                    "entities": [
                        {"type": "circle", "center": [rx, 0],
                         "diameter": inner_radius},
                    ],
                },
                "depth": thickness,
                "direction": "+Y",
            },
        ),
    ]


# ---------- Frame tubes ----------

def tube(
    fid: str,
    *,
    start: Sequence[str],
    end: Sequence[str],
    radius: str = "frame_tube_radius",
    depth: Optional[str] = None,
    plane: str = "XZ",
    direction: str = "+X",
) -> CADFeature:
    """Return an extrude_add that produces a single frame tube.

    ``start`` and ``end`` are 2-D sketch centres.  ``depth`` is
    the extrusion length.  When ``depth`` is omitted it is
    derived from the axis-aligned distance between the two
    centres; the compiler substitutes the resolved parameter
    reference, so ``"end-start"`` and ``"name"`` are both valid.
    For non-axis-aligned tubes pass ``depth`` explicitly.
    """
    if len(start) != 2 or len(end) != 2:
        raise ValueError("tube() start/end must be 2-D sketch coordinates")
    if depth is None:
        depth = _axis_aligned_length(start, end)
    return CADFeature(
        id=fid, type="extrude_add",
        parameters={
            "sketch": {
                "plane": plane,
                "entities": [
                    {"type": "circle", "center": list(start),
                     "diameter": radius},
                ],
            },
            "depth": depth,
            "direction": direction,
        },
    )


def _axis_aligned_length(start: Sequence[str], end: Sequence[str]) -> str:
    """Return a string expression of the form ``"end-start"``.

    For axis-aligned tubes the length is the absolute difference
    along one axis.  The compiler substitutes parameter
    references in this expression; callers that want a literal
    number can pass ``depth`` explicitly.
    """
    if str(start[0]) != str(end[0]):
        return f"{end[0]}-{start[0]}"
    if str(start[1]) != str(end[1]):
        return f"{end[1]}-{start[1]}"
    return "0.0"


# ---------- Handlebar, saddle, chainring ----------

def disc(
    fid: str,
    *,
    diameter: str,
    thickness: str,
    center: Sequence[str] = ("0", "0"),
    plane: str = "XY",
    direction: str = "+Z",
) -> CADFeature:
    """Return an extrude_add that produces a flat disc."""
    return CADFeature(
        id=fid, type="extrude_add",
        parameters={
            "sketch": {
                "plane": plane,
                "entities": [
                    {"type": "circle", "center": list(center),
                     "diameter": diameter},
                ],
            },
            "depth": thickness,
            "direction": direction,
        },
    )


# ---------- Top-level bicycle skeleton ----------

def bicycle_skeleton(
    *,
    wheel_radius: float = 220.0,
    wheel_thickness: float = 18.0,
    wheel_inner_radius: float = 195.0,
    frame_tube_radius: float = 9.0,
    stem_length: float = 70.0,
    handlebar_radius: float = 110.0,
    handlebar_thickness: float = 8.0,
    saddle_length: float = 130.0,
    saddle_thickness: float = 12.0,
    chainring_radius: float = 50.0,
    chainring_thickness: float = 5.0,
    bb_drop_z: float = 75.0,
    head_top_x: float = 200.0,
    head_top_z: float = 280.0,
    rear_axle_x: float = -230.0,
    rear_axle_z: float = 220.0,
) -> CADIR:
    """Build a CAD-IR document for a parameterised bicycle.

    The returned :class:`CADIR` follows the v0 schema.  Each
    bicycle tube is an extrude_add with an explicit ``depth``
    parameter (no arithmetic expressions in the IR) so the
    compiler can resolve every reference cleanly.
    """
    cad_ir = CADIR(name="bicycle", units="mm")
    cad_ir.add_parameter("wheel_radius", wheel_radius)
    cad_ir.add_parameter("wheel_thickness", wheel_thickness)
    cad_ir.add_parameter("wheel_inner_radius", wheel_inner_radius)
    cad_ir.add_parameter("frame_tube_radius", frame_tube_radius)
    cad_ir.add_parameter("bb_drop_z", bb_drop_z)
    cad_ir.add_parameter("head_top_x", head_top_x)
    cad_ir.add_parameter("head_top_z", head_top_z)
    cad_ir.add_parameter("rear_axle_x", rear_axle_x)
    cad_ir.add_parameter("rear_axle_z", rear_axle_z)
    cad_ir.add_parameter("stem_length", stem_length)
    cad_ir.add_parameter("handlebar_radius", handlebar_radius)
    cad_ir.add_parameter("handlebar_thickness", handlebar_thickness)
    cad_ir.add_parameter("saddle_length", saddle_length)
    cad_ir.add_parameter("saddle_thickness", saddle_thickness)
    cad_ir.add_parameter("chainring_radius", chainring_radius)
    cad_ir.add_parameter("chainring_thickness", chainring_thickness)

    # Wheels
    for f in wheel_pair(
        front_axle=("head_top_x", "0"),
        rear_axle=("rear_axle_x", "0"),
    ):
        cad_ir.add_feature(f)

    # Frame tubes.  Each tube uses an explicit depth parameter so
    # the compiler never has to evaluate an arithmetic expression.
    cad_ir.add_feature(tube(
        "down_tube",
        start=("0", "bb_drop_z"),
        end=("head_top_x", "bb_drop_z"),
        depth="head_top_x",
        direction="+X",
    ))
    cad_ir.add_feature(tube(
        "seat_tube",
        start=("0", "bb_drop_z"),
        end=("0", "head_top_z"),
        depth="head_top_z",
        direction="+Z",
    ))
    # Chainstay spans from the bottom bracket to the rear axle;
    # the depth is the absolute x-distance (handles negative
    # rear_axle_x via the magnitudes on each side).
    chainstay_length = abs(0.0 - rear_axle_x)
    cad_ir.add_feature(tube(
        "chainstay",
        start=("rear_axle_x", "0"),
        end=("0", "0"),
        depth=chainstay_length,
        direction="+X",
    ))
    # Seatstay spans from the rear axle up to the seat-top
    # position; depth is the absolute x-distance.
    seatstay_length = abs(0.0 - rear_axle_x)
    cad_ir.add_feature(tube(
        "seatstay",
        start=("rear_axle_x", "rear_axle_z"),
        end=("0", "head_top_z"),
        depth=seatstay_length,
        direction="+X",
    ))
    cad_ir.add_feature(tube(
        "head_tube",
        start=("0", "0"),
        end=("0", "head_top_z"),
        depth="head_top_z",
        direction="+Z",
    ))
    cad_ir.add_feature(tube(
        "stem",
        start=("head_top_x", "0"),
        end=("head_top_x", "stem_length"),
        depth="stem_length",
        direction="+Z",
    ))

    # Handlebar, saddle, chainring
    cad_ir.add_feature(disc(
        "handlebar", diameter="handlebar_radius",
        thickness="handlebar_thickness",
    ))
    cad_ir.add_feature(disc(
        "saddle", diameter="saddle_length",
        thickness="saddle_thickness",
    ))
    cad_ir.add_feature(disc(
        "chainring", diameter="chainring_radius",
        thickness="chainring_thickness",
    ))

    cad_ir.acceptance = {
        "bbox": [430, 200, 350],
        "must_have": [
            "wheels", "frame", "saddle", "handlebar", "chainring",
        ],
        "tolerance_mm": 1.0,
    }
    return cad_ir
