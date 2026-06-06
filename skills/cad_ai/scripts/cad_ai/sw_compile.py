"""CAD-IR v0/v1 -> SOLIDWORKS instruction stream.

This module does NOT call any COM API.  It only translates the IR
into a JSON document that a SOLIDWORKS backend consumes.  See
`contracts/cad_ir_to_sw_contract.md` for the contract.

The compiler is intentionally narrow: it only knows the v0/v1
whitelist.  Anything outside is rejected with a clear error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .ir_validate import validate_ir


SCHEMA = "sw_instructions.v0"

# Selector kinds the SOLIDWORKS backend understands (mirroring the
# cad_ai fillet/chamfer whitelist).
SUPPORTED_SELECTORS = ("all_edges", "top_outer_edges", "bottom_outer_edges")


def _py(value, params):
    """Render a JSON value as a JSON literal.  Identifiers that
    resolve to parameters are substituted with their numeric value;
    this means the instruction stream never carries parameter
    references -- it is fully resolved.
    """
    if isinstance(value, str):
        if value in params:
            return params[value]
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_py(x, params) for x in value]
    if isinstance(value, dict):
        return {k: _py(v, params) for k, v in value.items()}
    return value


def _sketch_operations(sk, params, to_metres=1.0):
    """Translate one sketch block into a list of operations.

    Lengths (size / diameter / radius) are converted from the
    user-facing unit to metres via ``to_metres`` so the swa
    backend receives SI units.
    """
    plane = sk["plane"]
    ops = [{"op": "select_plane", "plane": plane}]
    ops.append({"op": "sketch_begin"})
    for ent in sk["entities"]:
        et = ent["type"]
        if et == "center_rectangle":
            size = _py(ent["size"], params)
            if isinstance(size, (list, tuple)) and len(size) == 2:
                size = [float(s) * to_metres for s in size]
            center = _py(ent["center"], params)
            if isinstance(center, (list, tuple)) and len(center) == 2:
                center = [float(c) * to_metres for c in center]
            ops.append({
                "op": "sketch_rectangle",
                "center": center,
                "size": size,
            })
        elif et == "polygon":
            radius = _py(ent["radius"], params)
            if isinstance(radius, (int, float)):
                radius = float(radius) * to_metres
            center = _py(ent["center"], params)
            if isinstance(center, (list, tuple)) and len(center) == 2:
                center = [float(c) * to_metres for c in center]
            ops.append({
                "op": "sketch_polygon",
                "center": center,
                "radius": radius,
                "sides": _py(ent["sides"], params),
            })
        elif et == "circle":
            diameter = _py(ent["diameter"], params)
            if isinstance(diameter, (int, float)):
                diameter = float(diameter) * to_metres
            center = _py(ent["center"], params)
            if isinstance(center, (list, tuple)) and len(center) == 2:
                center = [float(c) * to_metres for c in center]
            ops.append({
                "op": "sketch_circle",
                "center": center,
                "diameter": diameter,
            })
        elif et == "circle_pattern":
            diameter = _py(ent["diameter"], params)
            if isinstance(diameter, (int, float)):
                diameter = float(diameter) * to_metres
            centers = _py(ent["centers"], params)
            new_centers = []
            for c in (centers or []):
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    new_centers.append([float(x) * to_metres for x in c])
                else:
                    new_centers.append(c)
            ops.append({
                "op": "sketch_circle_pattern",
                "centers": new_centers,
                "diameter": diameter,
            })
        else:
            raise ValueError(f"unsupported sketch entity: {et!r}")
    ops.append({"op": "sketch_end"})
    return ops


def compile_sw(doc):
    """Translate a CAD-IR dict to a SW instruction stream dict."""
    v = validate_ir(doc)
    if not v["ok"]:
        raise ValueError(f"IR validation failed: {v['errors']}")

    params = doc["parameters"]
    features = doc["features"]
    # The IR carries dimensions in the user-facing unit
    # (``doc["units"]``); the SOLIDWORKS backend (swa) consumes
    # the same values in metres.  v0 supports ``mm``, ``cm``,
    # ``m``; unknown units are rejected.
    units = (doc.get("units") or "mm").lower()
    if units == "mm":
        to_metres = 1e-3
    elif units == "cm":
        to_metres = 1e-2
    elif units == "m":
        to_metres = 1.0
    else:
        raise ValueError(f"unsupported units: {units!r}")

    doc_type = doc["document"].get("type", "part")
    if doc_type == "assembly":
        ops = [{"op": "new_assembly", "name": doc["document"].get("name", "assembly")}]
    elif doc_type == "drawing":
        ops = [{"op": "new_drawing", "name": doc["document"].get("name", "drawing")}]
    else:
        ops = [{"op": "new_part", "name": doc["document"].get("name", "part")}]
    extrude_adds = [f for f in features if f["type"] == "extrude_add"]
    if not extrude_adds:
        raise ValueError("v0 IR requires at least one extrude_add feature")

    for base in extrude_adds:
        ops.extend(_sketch_operations(base["sketch"], params, to_metres))
        base_depth = _py(base["depth"], params)
        if isinstance(base_depth, (int, float)):
            base_depth = float(base_depth) * to_metres
        direction = base.get("direction", "+Z")
        # Forward the feature id so the SW host can build a
        # feature_id -> feature object map.  A subtractive op
        # (extrude_cut, hole_through) with a target field can
        # then look up the targeted body instead of falling back
        # to "cut the active body" (the v0 approximation).
        ops.append({
            "op": "extrude",
            "feature_id": base.get("id"),
            "depth": base_depth,
            "direction": direction,
        })
    for feat in features:
        if feat["type"] == "extrude_add":
            continue
        ftype = feat["type"]
        if ftype == "hole_through":
            axis = feat.get("axis", "Z")
            if axis != "Z":
                raise ValueError(
                    f"{feat['id']}: SW backend v0 only supports Z-axis through-holes"
                )
            ops.append({"op": "select_face", "selector": {"kind": "top_face"}})
            ops.append({"op": "sketch_begin"})
            diameter = _py(feat["diameter"], params)
            if isinstance(diameter, (int, float)):
                diameter = float(diameter) * to_metres
            center = _py(feat["position"], params)
            if isinstance(center, (list, tuple)) and len(center) == 2:
                center = [float(c) * to_metres for c in center]
            ops.append({
                "op": "sketch_circle",
                "center": center,
                "diameter": diameter,
            })
            ops.append({"op": "sketch_end"})
            ops.append({
                "op": "extrude_cut",
                "target": feat.get("target"),
                "depth": "through",
            })
        elif ftype == "extrude_cut":
            ops.extend(_sketch_operations(feat["sketch"], params, to_metres))
            depth = _py(feat["depth"], params)
            if isinstance(depth, (int, float)):
                depth = float(depth) * to_metres
            ops.append({
                "op": "extrude_cut",
                "target": feat.get("target"),
                "depth": depth,
            })
        elif ftype in ("fillet", "chamfer"):
            sel = feat.get("selector", {}) or {}
            kind = sel.get("kind", "all_edges")
            if kind not in SUPPORTED_SELECTORS:
                raise ValueError(f"unsupported selector kind: {kind!r}")
            if ftype == "fillet":
                radius = _py(feat.get("radius"), params)
                if isinstance(radius, (int, float)):
                    radius = float(radius) * to_metres
                ops.append({
                    "op": "fillet",
                    "radius": radius,
                    "selector": {"kind": kind},
                })
            else:
                size = _py(feat.get("size"), params)
                if isinstance(size, (int, float)):
                    size = float(size) * to_metres
                ops.append({
                    "op": "chamfer",
                    "size": size,
                    "selector": {"kind": kind},
                })
        elif ftype == "join_bodies":
            # v0.2: boolean assembly is emitted after all other ops
            pass
        elif ftype == 'revolve':
            ops.extend(_sketch_operations(feat['sketch'], params, to_metres))
            angle = _py(feat.get('angle', 360), params)
            if isinstance(angle, (int, float)):
                angle = float(angle)
            ops.append({
                'op': 'revolve',
                'feature_id': feat.get('id'),
                'angle': angle,
                'axis': feat.get('axis', '+Z'),
                'cut': feat.get('cut', False),
            })
        elif ftype == 'loft':
            profiles = feat.get('profiles', [])
            for profile in profiles:
                ops.extend(_sketch_operations(profile.get('sketch', {}), params, to_metres))
            ops.append({
                'op': 'loft_boss' if not feat.get('cut', False) else 'loft_cut',
                'feature_id': feat.get('id'),
                'closed': feat.get('closed', False),
                'profile_count': len(profiles),
            })
        elif ftype == 'mirror':
            ops.append({
                'op': 'mirror',
                'features': _py(feat['features'], params),
                'plane': feat.get('plane', 'YZ'),
            })
        elif ftype == 'linear_pattern':
            spacing = _py(feat['spacing'], params)
            if isinstance(spacing, (int, float)):
                spacing = float(spacing) * to_metres
            count = int(_py(feat['count'], params))
            ops.append({
                'op': 'linear_pattern',
                'features': _py(feat['features'], params),
                'direction': feat.get('direction', 'X'),
                'spacing': spacing,
                'count': count,
            })
        elif ftype == 'circular_pattern':
            angle = _py(feat.get('angle', 360), params)
            if isinstance(angle, (int, float)):
                angle = float(angle)
            count = int(_py(feat['count'], params))
            ops.append({
                'op': 'circular_pattern',
                'features': _py(feat['features'], params),
                'axis': feat.get('axis', 'Z'),
                'count': count,
                'angle': angle,
            })
        elif ftype == 'shell':
            thickness = _py(feat['thickness'], params)
            if isinstance(thickness, (int, float)):
                thickness = float(thickness) * to_metres
            faces = _py(feat.get('faces', []), params)
            ops.append({
                'op': 'shell',
                'thickness': thickness,
                'faces': faces if isinstance(faces, list) else [],
            })
        elif ftype == 'draft':
            angle = _py(feat['angle'], params)
            if isinstance(angle, (int, float)):
                angle = float(angle)
            faces = _py(feat.get('faces', []), params)
            ops.append({
                'op': 'draft',
                'angle': angle,
                'direction': feat.get('direction', '+Z'),
                'faces': faces if isinstance(faces, list) else [],
            })
        elif ftype == 'loft_surface':
            profiles = feat.get('profiles', [])
            for profile in profiles:
                ops.extend(_sketch_operations(profile.get('sketch', {}), params, to_metres))
            ops.append({
                'op': 'loft_surface',
                'feature_id': feat.get('id'),
                'closed': feat.get('closed', False),
                'profile_count': len(profiles),
            })
        elif ftype == 'thicken':
            thickness = _py(feat['thickness'], params)
            if isinstance(thickness, (int, float)):
                thickness = float(thickness) * to_metres
            ops.append({
                'op': 'thicken',
                'surface': feat.get('surface', ''),
                'thickness': thickness,
                'direction': feat.get('direction', '+Z'),
            })
        elif ftype == 'fill_surface':
            boundary = _py(feat.get('boundary', []), params)
            ops.append({
                'op': 'fill_surface',
                'boundary': boundary if isinstance(boundary, list) else [],
            })
        elif ftype == 'knit':
            surfaces = _py(feat.get('surfaces', []), params)
            ops.append({
                'op': 'knit',
                'surfaces': surfaces if isinstance(surfaces, list) else [],
            })
        elif ftype == 'add_component':
            x = float(_py(feat.get('x', 0), params)) * to_metres
            y = float(_py(feat.get('y', 0), params)) * to_metres
            z = float(_py(feat.get('z', 0), params)) * to_metres
            ops.append({
                'op': 'add_component',
                'feature_id': feat.get('id'),
                'path': feat.get('path', ''),
                'x': x, 'y': y, 'z': z,
            })
        elif ftype == 'mate_coincident':
            ops.append({
                'op': 'mate_coincident',
                'component_a': feat.get('component_a', ''),
                'feature_a': feat.get('feature_a', ''),
                'component_b': feat.get('component_b', ''),
                'feature_b': feat.get('feature_b', ''),
            })
        elif ftype == 'mate_concentric':
            ops.append({
                'op': 'mate_concentric',
                'component_a': feat.get('component_a', ''),
                'feature_a': feat.get('feature_a', ''),
                'component_b': feat.get('component_b', ''),
                'feature_b': feat.get('feature_b', ''),
            })
        elif ftype == 'mate_distance':
            distance = float(_py(feat['distance'], params)) * to_metres
            ops.append({
                'op': 'mate_distance',
                'component_a': feat.get('component_a', ''),
                'feature_a': feat.get('feature_a', ''),
                'component_b': feat.get('component_b', ''),
                'feature_b': feat.get('feature_b', ''),
                'distance': distance,
            })
        elif ftype == 'add_view':
            x = float(_py(feat.get('x', 0), params)) * to_metres
            y = float(_py(feat.get('y', 0), params)) * to_metres
            scale = float(_py(feat.get('scale', 1), params))
            ops.append({
                'op': 'add_view',
                'model': feat.get('model', ''),
                'view_type': feat.get('view_type', 'front'),
                'x': x, 'y': y, 'scale': scale,
            })
        elif ftype == 'add_dimension':
            value = float(_py(feat['value'], params)) * to_metres
            ops.append({
                'op': 'add_dimension',
                'entity_a': feat.get('entity_a', ''),
                'entity_b': feat.get('entity_b', ''),
                'value': value,
            })
        elif ftype == 'equation':
            ops.append({
                'op': 'equation',
                'name': feat.get('name', ''),
                'expression': feat.get('expression', ''),
            })
        elif ftype == 'generate_bom':
            ops.append({
                'op': 'generate_bom',
                'format': feat.get('format', 'json'),
                'output_path': feat.get('output_path', ''),
            })
        elif ftype == 'add_configuration':
            ops.append({
                'op': 'add_configuration',
                'name': feat.get('name', ''),
                'description': feat.get('description', ''),
                'parent': feat.get('parent', ''),
            })
        elif ftype == 'set_configuration':
            ops.append({
                'op': 'set_configuration',
                'name': feat.get('name', ''),
            })
        elif ftype == 'suppress_feature':
            ops.append({
                'op': 'suppress_feature',
                'feature': feat.get('feature', ''),
                'configuration': feat.get('configuration', ''),
            })
        elif ftype == 'design_table':
            ops.append({
                'op': 'design_table',
                'rows': feat.get('rows', []),
                'columns': feat.get('columns', []),
            })
        elif ftype == 'sweep':
            # v0.7: SW sweep support via perpendicular plane + 3D sketch
            sk = feat.get('profile', {}).get('sketch', {})
            path = feat.get('path', {})
            ops.extend(_sketch_operations(sk, params, to_metres))
            ops.append({
                'op': 'sketch_3d_path',
                'start': _py(path['start'], params),
                'end': _py(path['end'], params),
                'feature_id': feat.get('id'),
            })
            ops.append({
                'op': 'sweep_boss',
                'feature_id': feat.get('id'),
                'merge': True,
            })
        else:
            raise ValueError(f"unsupported feature type: {ftype!r}")
    # v0.2: boolean assembly -- join all bodies into one
    if any(f.get('type') == 'join_bodies' for f in features):
        ops.append({'op': 'boolean_union', 'all': True})

    return {
        "schema": SCHEMA,
        "document": "part",
        "operations": ops,
    }


def main(argv):
    if len(argv) < 2:
        print("Usage: sw_compile.py <cad-ir.json> [-o <output.json>]", file=sys.stderr)
        return 2
    src = Path(argv[1])
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 >= len(argv):
            print("sw_compile.py: -o requires a path", file=sys.stderr)
            return 2
        out = Path(argv[i + 1])
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"sw_compile.py: failed to read {src}: {exc}", file=sys.stderr)
        return 2
    try:
        stream = compile_sw(doc)
    except ValueError as exc:
        print(f"sw_compile.py: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(stream, indent=2)
    if out is None:
        sys.stdout.write(text + "\n")
        return 0
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
