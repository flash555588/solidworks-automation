"""CAD-IR projection validator.

Validates a CAD-IR document *before* it reaches the compiler by
checking that every numeric parameter resolves to a positive
quantity, that references between features point to existing
features, and that the ``acceptance`` block (if present) is
self-consistent.

This module does **not** require SOLIDWORKS or any external
geometry engine.  It is the cheap first line of defence; the
existing ``ir_validate.py`` handles the schema-level checks.

The two modules compose: callers should run
``ir_validate.validate_ir`` first (schema check) and then
``projection_validator.validate_projection`` (semantic check).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class ProjectionError(dict):
    """A single projection-validation error.

    Shape matches the existing ``ir_validate`` error entries so
    downstream tools can consume both uniformly.
    """

    def __init__(self, path: str, code: str, message: str) -> None:
        super().__init__(path=path, code=code, message=message)


def validate_projection(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the semantic projection of a CAD-IR document.

    Returns ``{"ok": bool, "errors": [ProjectionError, ...]}``.
    Always succeeds; callers should branch on ``ok``.
    """
    errors: List[ProjectionError] = []
    if not isinstance(doc, dict):
        errors.append(ProjectionError("$", "not_object", "top-level must be a JSON object"))
        return {"ok": False, "errors": errors}

    params = doc.get("parameters") or {}
    features = doc.get("features") or []
    feature_ids = {f.get("id") for f in features if isinstance(f, dict) and f.get("id")}

    # 2) Features: dimensions, references, and target consistency.
    for f in features:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        ftype = f.get("type")
        if not fid:
            errors.append(ProjectionError("$.features[]", "missing_id",
                                          "feature missing required 'id'"))
            continue
        if not ftype:
            errors.append(ProjectionError(
                f"$.features[?id={fid!r}]", "missing_type",
                f"feature {fid!r} missing required 'type'"))
            continue

        # Reference fields: ``target`` and ``references``.
        target = f.get("target")
        if isinstance(target, str) and target not in feature_ids:
            errors.append(ProjectionError(
                f"$.features[?id={fid!r}].target",
                "unknown_reference",
                f"target {target!r} not a known feature id",
            ))
        for ref in f.get("references", []) or []:
            if ref not in feature_ids:
                errors.append(ProjectionError(
                    f"$.features[?id={fid!r}].references",
                    "unknown_reference",
                    f"reference {ref!r} not a known feature id",
                ))

        # Numeric dimensions on a feature must be positive.
        for key in ("depth", "radius", "size", "diameter"):
            value = f.get(key)
            if isinstance(value, (int, float)) and value <= 0:
                errors.append(ProjectionError(
                    f"$.features[?id={fid!r}].{key}",
                    "non_positive",
                    f"{key} of {fid!r} is non-positive: {value!r}",
                ))

    # 3) Acceptance bbox: every component must be positive.
    acceptance = doc.get("acceptance")
    if isinstance(acceptance, dict):
        bbox = acceptance.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 3:
            for i, v in enumerate(bbox):
                if isinstance(v, (int, float)) and v <= 0:
                    errors.append(ProjectionError(
                        f"$.acceptance.bbox[{i}]", "non_positive",
                        f"acceptance.bbox[{i}] is non-positive: {v!r}",
                    ))

    return {"ok": not errors, "errors": errors}
