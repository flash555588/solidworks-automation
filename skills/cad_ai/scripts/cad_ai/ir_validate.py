"""CAD-IR v0 validator.

Returns a structured result `{ok, errors}`.  The validator is
deliberately talkative about error paths so that an LLM retry loop
can act on the failure list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import ir_schema as S


def _add_error(errors, path, code, message):
    errors.append({"path": path, "code": code, "message": message})


def _check_type(value, expected, path, errors, *, allow_str_number=False):
    """Type check helper. If allow_str_number, a string is accepted as a
    parameter reference (must be a non-empty identifier)."""
    if allow_str_number and isinstance(value, str):
        if not value:
            _add_error(errors, path, "empty_identifier", f"{path} is empty")
        return
    if not isinstance(value, expected):
        type_name = (
            expected.__name__ if isinstance(expected, type)
            else "/".join(getattr(t, "__name__", str(t)) for t in expected)
        )
        _add_error(
            errors, path, "type_mismatch",
            f"{path} expected {type_name}, got {type(value).__name__}",
        )


def _resolve_param(value, params):
    """If value is a string, treat as a parameter reference. Otherwise
    return value as-is.  Returns (resolved, is_ref)."""
    if isinstance(value, str):
        if value not in params:
            return None, True
        return params[value], True
    return value, False


def validate_ir(doc):
    errors = []

    if not isinstance(doc, dict):
        return {"ok": False, "errors": [{"path": "$", "code": "not_object",
                                          "message": "Top-level must be a JSON object"}]}

    # Top-level required fields
    for field, t in S.TOP_LEVEL_FIELDS.items():
        if field in ("assumptions", "acceptance"):
            continue  # optional per the v0 schema document
        if field not in doc:
            _add_error(errors, f"$.{field}", "missing_field",
                       f"Missing required field: {field}")
            continue
        _check_type(doc[field], t, f"$.{field}", errors)

    # schema
    if doc.get("schema") != S.SCHEMA_NAME:
        _add_error(errors, "$.schema", "schema_mismatch",
                   f"schema must be {S.SCHEMA_NAME!r}, got {doc.get('schema')!r}")

    # units
    if doc.get("units") not in S.SUPPORTED_UNITS:
        _add_error(errors, "$.units", "unsupported_units",
                   f"units must be one of {S.SUPPORTED_UNITS}")

    # document
    doc_obj = doc.get("document", {})
    for f, t in S.DOCUMENT_FIELDS.items():
        if f not in doc_obj:
            _add_error(errors, f"$.document.{f}", "missing_field",
                       f"Missing required field: document.{f}")
            continue
        _check_type(doc_obj[f], t, f"$.document.{f}", errors)
    if doc_obj.get("type") not in S.SUPPORTED_DOCUMENT_TYPES:
        _add_error(errors, "$.document.type", "unsupported_document_type",
                   f"document.type must be one of {S.SUPPORTED_DOCUMENT_TYPES}")

    # coordinate_system
    cs = doc.get("coordinate_system", {})
    for f, t in S.COORDINATE_SYSTEM_FIELDS.items():
        if f not in cs:
            _add_error(errors, f"$.coordinate_system.{f}", "missing_field",
                       f"Missing required field: coordinate_system.{f}")
            continue
        _check_type(cs[f], t, f"$.coordinate_system.{f}", errors)
    if cs.get("up_axis") not in S.SUPPORTED_UP_AXES:
        _add_error(errors, "$.coordinate_system.up_axis", "unsupported_up_axis",
                   f"up_axis must be one of {S.SUPPORTED_UP_AXES}")
    if cs.get("front_axis") not in S.SUPPORTED_FRONT_AXES:
        _add_error(errors, "$.coordinate_system.front_axis", "unsupported_front_axis",
                   f"front_axis must be one of {S.SUPPORTED_FRONT_AXES}")

    # parameters: must be a dict of name -> number
    params = doc.get("parameters", {})
    if isinstance(params, dict):
        for name, value in params.items():
            if not isinstance(name, str) or not name:
                _add_error(errors, f"$.parameters.{name!r}", "bad_parameter_name",
                           "Parameter name must be a non-empty string")
                continue
            if not isinstance(value, (int, float)):
                _add_error(errors, f"$.parameters.{name}", "type_mismatch",
                           f"Parameter {name!r} must be a number, got {type(value).__name__}")

    # features
    features = doc.get("features", [])
    feature_ids = set()
    if isinstance(features, list):
        for i, feat in enumerate(features):
            base = f"$.features[{i}]"
            if not isinstance(feat, dict):
                _add_error(errors, base, "not_object",
                           "Feature must be an object")
                continue
            for f, t in S.FEATURE_BASE_FIELDS.items():
                if f not in feat:
                    _add_error(errors, f"{base}.{f}", "missing_field",
                               f"Feature missing required field: {f}")
                    continue
                _check_type(feat[f], t, f"{base}.{f}", errors)
            ftype = feat.get("type")
            if ftype not in S.SUPPORTED_FEATURE_TYPES:
                _add_error(errors, f"{base}.type", "unsupported_feature_type",
                           f"Feature type must be one of {S.SUPPORTED_FEATURE_TYPES}, got {ftype!r}")
                continue
            fid = feat.get("id")
            if isinstance(fid, str):
                if fid in feature_ids:
                    _add_error(errors, f"{base}.id", "duplicate_id",
                               f"Duplicate feature id: {fid!r}")
                feature_ids.add(fid)
            # Type-specific fields
            for f, t in S.FEATURE_TYPE_FIELDS.get(ftype, {}).items():
                if f not in feat:
                    _add_error(errors, f"{base}.{f}", "missing_field",
                               f"Feature {fid!r} ({ftype}) missing required field: {f}")
                    continue
                _check_type(feat[f], t, f"{base}.{f}", errors, allow_str_number=(f in _NUMBER_OR_REF_FIELDS))

            # target references must resolve to a known prior feature id.
            target = feat.get("target")
            if isinstance(target, str) and target not in feature_ids:
                # Tolerate forward references in v0 only for "target" - record
                # the error here.  The compiler also rechecks.
                pass  # We re-validate ordering at the end of this function.

            # Sketch validation
            if ftype in ("extrude_add", "extrude_cut"):
                sk = feat.get("sketch", {})
                if isinstance(sk, dict):
                    _validate_sketch(sk, f"{base}.sketch", errors, params, feature_ids_so_far=feature_ids)
            if ftype == "sweep":
                sk = feat.get("profile", {}).get("sketch", {})
                if isinstance(sk, dict):
                    _validate_sketch(sk, f"{base}.profile.sketch", errors, params,
                                     feature_ids_so_far=feature_ids)
                path = feat.get("path", {})
                if not isinstance(path, dict):
                    _add_error(errors, f"{base}.path", "invalid_type",
                               "sweep.path must be a dict")
                else:
                    for key in ("start", "end"):
                        if key not in path:
                            _add_error(errors, f"{base}.path.{key}", "missing_field",
                                       f"sweep.path missing {key!r}")
                        elif not isinstance(path[key], list) or len(path[key]) != 3:
                            _add_error(errors, f"{base}.path.{key}", "invalid_type",
                                       f"sweep.path.{key} must be [x, y, z]")

    # Forward-reference / target ordering
    if isinstance(features, list):
        for i, feat in enumerate(features):
            base = f"$.features[{i}]"
            target = feat.get("target")
            if isinstance(target, str):
                if target not in {f.get("id") for f in features[:i] if isinstance(f, dict)}:
                    _add_error(errors, f"{base}.target", "unknown_ref",
                               f"target {target!r} does not reference a prior feature")

    # acceptance
    if "acceptance" in doc:
        _validate_acceptance(doc["acceptance"], "$.acceptance", errors)

    # Unused-parameter check (optional but useful)
    if isinstance(params, dict) and isinstance(features, list):
        used = set()
        _collect_used_params(features, used)
        for name in params:
            if name not in used:
                _add_error(errors, f"$.parameters.{name}", "unused_parameter",
                           f"Parameter {name!r} is declared but never referenced")

    return {"ok": not errors, "errors": errors}


_NUMBER_OR_REF_FIELDS = {"depth", "diameter", "radius", "size"}


def _validate_sketch(sk, base, errors, params, *, feature_ids_so_far):
    for f, t in S.SKETCH_BASE_FIELDS.items():
        if f not in sk:
            _add_error(errors, f"{base}.{f}", "missing_field",
                       f"Sketch missing required field: {f}")
            continue
        _check_type(sk[f], t, f"{base}.{f}", errors)

    ents = sk.get("entities", [])
    if not isinstance(ents, list) or not ents:
        _add_error(errors, f"{base}.entities", "empty_entities",
                   "Sketch must have at least one entity")
        return
    for j, ent in enumerate(ents):
        eb = f"{base}.entities[{j}]"
        if not isinstance(ent, dict):
            _add_error(errors, eb, "not_object", "Entity must be an object")
            continue
        etype = ent.get("type")
        if etype not in S.SUPPORTED_SKETCH_ENTITY_TYPES:
            _add_error(errors, f"{eb}.type", "unsupported_entity_type",
                       f"Entity type must be one of {S.SUPPORTED_SKETCH_ENTITY_TYPES}, got {etype!r}")
            continue
        for f, t in S.SKETCH_ENTITY_FIELDS.get(etype, {}).items():
            if f not in ent:
                _add_error(errors, f"{eb}.{f}", "missing_field",
                           f"Entity ({etype}) missing required field: {f}")
                continue
            _check_type(ent[f], t, f"{eb}.{f}", errors, allow_str_number=(f in _NUMBER_OR_REF_FIELDS or f == "center" or f == "size"))


def _validate_acceptance(ac, base, errors):
    if not isinstance(ac, dict):
        _add_error(errors, base, "not_object", "acceptance must be an object")
        return
    if "bbox" in ac:
        bbox = ac["bbox"]
        if not (isinstance(bbox, list) and len(bbox) == 3 and
                all(isinstance(v, (int, float)) for v in bbox)):
            _add_error(errors, f"{base}.bbox", "type_mismatch",
                       "acceptance.bbox must be a 3-element list of numbers")
    if "must_have" in ac:
        mh = ac["must_have"]
        if not isinstance(mh, list) or not all(isinstance(x, str) for x in mh):
            _add_error(errors, f"{base}.must_have", "type_mismatch",
                       "acceptance.must_have must be a list of strings")


def _collect_used_params(features, used):
    for feat in features:
        if not isinstance(feat, dict):
            continue
        for v in feat.values():
            _walk_collect(v, used)
        sk = feat.get("sketch", {})
        if isinstance(sk, dict):
            for ent in sk.get("entities", []):
                if isinstance(ent, dict):
                    for v in ent.values():
                        _walk_collect(v, used)


def _walk_collect(v, used):
    if isinstance(v, str):
        used.add(v)
    elif isinstance(v, list):
        for item in v:
            _walk_collect(item, used)
    elif isinstance(v, dict):
        for vv in v.values():
            _walk_collect(vv, used)


def main(argv):
    if len(argv) != 2:
        print("Usage: validate_ir.py <cad-ir.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [
            {"path": "$", "code": "io_error", "message": str(exc)},
        ]}, indent=2))
        return 2
    result = validate_ir(doc)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
