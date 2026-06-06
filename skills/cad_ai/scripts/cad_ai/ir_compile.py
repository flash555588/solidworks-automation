"""CAD-IR v0/v1.1 compiler -> build123d Python source.

v1.1 changes from v1:

- Multiple `extrude_add` features are now allowed.  The first
  extrude_add establishes the BuildPart; subsequent extrude_add
  features each emit an additional `extrude(...)` inside the same
  BuildPart context, placed at a Z offset via the sketch plane.
- `extrude_add` may carry a `z_offset` field (number or parameter
  reference).  When present, the sketch is drawn on
  `Plane.XY.offset(z_offset)`.  When absent (the v1 default), the
  sketch is on `Plane.XY` (Z=0).
- Every `extrude_add` now requires its `depth` to be a parameter
  reference.  This is so a subtractive helper can look up a
  default target thickness; literal numbers are rejected.

The CAD-IR schema, validator, and tests are unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import ir_schema as S
from .ir_validate import validate_ir


def _py(value, params, used):
    if isinstance(value, str):
        if value in params:
            used.add(value)
            return f"params[{value!r}]"
        return repr(value)
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_py(x, params, used) for x in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {_py(v, params, used)}"
                                for k, v in value.items()) + "}"
    return repr(value)


def _emit_center_rectangle(ent, params, used, *, indent):
    cx_s = _py(ent["center"][0], params, used)
    cy_s = _py(ent["center"][1], params, used)
    w_s = _py(ent["size"][0], params, used)
    h_s = _py(ent["size"][1], params, used)
    return (f"{indent}with Locations(({cx_s}, {cy_s})):\n"
            f"{indent}    Rectangle({w_s}, {h_s})")


def _emit_circle(ent, params, used, *, indent):
    cx_s = _py(ent["center"][0], params, used)
    cy_s = _py(ent["center"][1], params, used)
    d_s = _py(ent["diameter"], params, used)
    return (f"{indent}with Locations(({cx_s}, {cy_s})):\n"
            f"{indent}    Circle({d_s} / 2)")


def _emit_circle_pattern(ent, params, used, *, indent):
    centers_s = _py(ent["centers"], params, used)
    d_s = _py(ent["diameter"], params, used)
    return (f"{indent}with Locations({centers_s}):\n"
            f"{indent}    Circle({d_s} / 2)")


def _emit_polygon(ent, params, used, *, indent):
    cx_s = _py(ent["center"][0], params, used)
    cy_s = _py(ent["center"][1], params, used)
    r_s = _py(ent["radius"], params, used)
    sides_s = _py(ent["sides"], params, used)
    return (f"{indent}with Locations(({cx_s}, {cy_s})):\n"
            f"{indent}    RegularPolygon({r_s}, {sides_s})")


def _emit_sketch_block(sk, params, used, *, prefix, override_plane=None):
    """Emit a `with BuildSketch(<plane>): ...` block.

    If `override_plane` is given, it is used verbatim.  Otherwise
    the plane is derived from the IR sketch field (`plane` plus
    `plane_offset`).
    """
    if override_plane is not None:
        plane_expr = override_plane
    else:
        plane = sk["plane"]
        if plane not in ("XY", "XZ", "YZ"):
            raise ValueError(f"unsupported plane: {plane!r}")
        plane_offset = sk.get("plane_offset", 0)
        if plane_offset:
            plane_expr = f"Plane.{plane}.offset({_py(plane_offset, params, used)})"
        else:
            plane_expr = f"Plane.{plane}"
    lines = [f"{prefix}with BuildSketch({plane_expr}):"]
    for ent in sk["entities"]:
        et = ent["type"]
        if et == "center_rectangle":
            lines.append(_emit_center_rectangle(ent, params, used,
                                                  indent=prefix + "    "))
        elif et == "polygon":
            lines.append(_emit_polygon(ent, params, used,
                                         indent=prefix + "    "))
        elif et == "circle":
            lines.append(_emit_circle(ent, params, used,
                                        indent=prefix + "    "))
        elif et == "circle_pattern":
            lines.append(_emit_circle_pattern(ent, params, used,
                                                indent=prefix + "    "))
        else:
            raise ValueError(
                f"v1 emitter: sketch entity {et!r} not implemented"
            )
    return "\n".join(lines)


def _emit_extrude_add_in_place(feat, params, used):
    """Emit a sketch+extrude pair that lives INSIDE an existing
    `with BuildPart() as bp:` context.  Caller is responsible for
    opening and closing the BuildPart.

    Honors the v1.1 `z_offset` field on the feature: if present,
    the sketch is drawn on `Plane.XY.offset(z_offset)`.  Otherwise
    the sketch is on Plane.XY (Z=0).
    """
    z_offset = feat.get("z_offset")
    if z_offset is not None:
        z_s = _py(z_offset, params, used)
        sk_lines = _emit_sketch_block(feat["sketch"], params, used,
                                       prefix="    ",
                                       override_plane=f"Plane.XY.offset({z_s})")
    else:
        sk_lines = _emit_sketch_block(feat["sketch"], params, used,
                                       prefix="    ")
    depth = _py(feat["depth"], params, used)
    return f"{sk_lines}\n    extrude(amount={depth})\n"


def _emit_subtractive_fn(feat, params, used, *, target_thickness_var, fn_index):
    fid = feat["id"]
    ftype = feat["type"]
    fn_name = f"_build_sub_{fn_index}"
    if ftype == "hole_through":
        d_s = _py(feat["diameter"], params, used)
        pos = feat["position"]
        axis = feat["axis"]
        if axis != "Z":
            raise ValueError(
                f"{fid}: v1 only supports through-holes along Z axis, got {axis!r}"
            )
        if not isinstance(pos, list) or len(pos) != 2:
            raise ValueError(f"{fid}: hole_through.position must be [x, y] in 2D")
        cx_s = _py(pos[0], params, used)
        cy_s = _py(pos[1], params, used)
        return (
            f"\ndef {fn_name}():\n"
            f"    with BuildPart() as _bp:\n"
            f"        with BuildSketch(Plane.XY):\n"
            f"            with Locations(({cx_s}, {cy_s})):\n"
            f"                Circle({d_s} / 2)\n"
            f"        extrude(amount={target_thickness_var} * 2)\n"
            f"    return _bp.part\n"
        )
    raise ValueError(f"unsupported subtractive type: {ftype!r}")


def _emit_fillet_or_chamfer(feat, params, used):
    r = _py(feat.get("radius", feat.get("size")), params, used)
    op = "fillet" if feat["type"] == "fillet" else "chamfer"
    return f"body = body.{op}({r})\n"


def _emit_sweep(feat, params, used, *, prefix="    "):
    sk = feat["profile"]["sketch"]
    sk_lines = _emit_sketch_block(sk, params, used, prefix=prefix)
    path = feat["path"]
    start_s = _py(path["start"], params, used)
    end_s = _py(path["end"], params, used)
    return (
        f"{sk_lines}\n"
        f"{prefix}path = Line({start_s}, {end_s})\n"
        f"{prefix}sweep(path=path)\n"
    )


def compile_ir(doc):
    v = validate_ir(doc)
    if not v["ok"]:
        raise ValueError(f"IR validation failed: {v['errors']}")

    params = doc["parameters"]
    features = doc["features"]
    used = set()

    extrude_adds = [f for f in features if f["type"] == "extrude_add"]
    sweeps = [f for f in features if f["type"] == "sweep"]
    if not extrude_adds:
        raise ValueError("v0 IR requires at least one extrude_add feature")

    # v1.1: every extrude_add must reference its depth as a
    # parameter (no literal numbers).  This makes a subtractive
    # helper able to look up a default target thickness.
    for ea in extrude_adds:
        if not isinstance(ea["depth"], str):
            raise ValueError(
                f"v1.1 IR: extrude_add {ea.get('id', '?')!r}.depth must reference a parameter"
            )
        if ea["depth"] not in params:
            raise ValueError(
                f"v1.1 IR: extrude_add {ea.get('id', '?')!r}.depth {ea['depth']!r} not in parameters"
            )

    header = (
        '"""Auto-generated by cad_ai/scripts/cad_ai/ir_compile.py.\n'
        'Do not edit by hand; regenerate from the CAD-IR.\n"""\n'
        "from __future__ import annotations\n\n"
        "from build123d import (\n"
        "    BuildPart, BuildSketch, Circle, Line, Locations, Mode, Part, Plane,\n"
        "    Rectangle, RegularPolygon, chamfer, extrude, fillet, sweep,\n"
        ")\n\n"
    )
    parts = [header, f"params = {params!r}\n\n"]

    # v1.1: subtractive helpers reference a default target thickness,
    # taken from the first extrude_add.  A future v1.2 will let
    # subtractives target a specific extrude_add by id.
    default_target = extrude_adds[0]["depth"]

    fn_index = 0
    for feat in features:
        if feat["type"] in ("extrude_cut", "hole_through"):
            parts.append(_emit_subtractive_fn(
                feat, params, used,
                target_thickness_var=f"params[{default_target!r}]",
                fn_index=fn_index,
            ))
            fn_index += 1

    # Main build: open BuildPart, emit every extrude_add, then take
    # `body = bp.part` and apply the algebra-mode operations.
    parts.append("\n# --- main build ---\n")
    parts.append("with BuildPart() as bp:\n")
    for ea in extrude_adds:
        parts.append(_emit_extrude_add_in_place(ea, params, used))
    for sw in sweeps:
        parts.append(_emit_sweep(sw, params, used))
    parts.append("\nbase = bp.part\nbody = base\n")

    sub_idx = 0
    for feat in features:
        if feat["type"] == "extrude_add":
            continue
        if feat["type"] in ("extrude_cut", "hole_through"):
            parts.append(f"body = body.cut(_build_sub_{sub_idx}())\n")
            sub_idx += 1
        elif feat["type"] in ("fillet", "chamfer"):
            parts.append(_emit_fillet_or_chamfer(feat, params, used))

    name = doc["document"].get("name", "part")
    parts.append(f"body.label = {name!r}\n")
    parts.append("\n\ndef gen_step():\n    return body\n")
    return "".join(parts)


def main(argv):
    if len(argv) < 2:
        print("Usage: compile_ir.py <cad-ir.json> [-o <output.py>]", file=sys.stderr)
        return 2
    src = Path(argv[1])
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 >= len(argv):
            print("compile_ir.py: -o requires a path", file=sys.stderr)
            return 2
        out = Path(argv[i + 1])
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except (OSOSError, json.JSONDecodeError) as exc:
        print(f"compile_ir.py: failed to read {src}: {exc}", file=sys.stderr)
        return 2
    try:
        emitted = compile_ir(doc)
    except ValueError as exc:
        print(f"compile_ir.py: {exc}", file=sys.stderr)
        return 1
    if out is None:
        sys.stdout.write(emitted)
        return 0
    out.write_text(emitted, encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
