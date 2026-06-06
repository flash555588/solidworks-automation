"""CAD-IR feature planner.

Orders features so that downstream compilers receive them in a
build-safe order:

    1. ``extrude_add`` / ``loft_base`` -- the bodies themselves
    2. ``extrude_cut`` / ``hole_through`` -- subtractive ops
       (depend on the parent body existing)
    3. ``fillet`` / ``chamfer`` -- post-finish operations
    4. ``pattern`` -- applied last

The planner is a thin layer that re-orders a :class:`CADIR`
``features`` list.  It does not invent new features; it does not
mutate parameters; it only assigns a deterministic order.
"""

from __future__ import annotations

from typing import Callable, List

from .schema import CADFeature, CADIR


_TYPE_BUCKETS: List[Callable[[str], bool]] = [
    # base / additive
    lambda t: t in ("extrude_add", "loft_base"),
    # subtractive
    lambda t: t in ("extrude_cut", "hole_through") or t.startswith("cut"),
    # finishing
    lambda t: t in ("fillet", "chamfer"),
    # patterns
    lambda t: t == "pattern",
]


def plan_feature_sequence(cad_ir: CADIR) -> List[CADFeature]:
    """Return a new list of features in build-safe order.

    The original ordering inside a bucket is preserved -- a stable
    sort is used so that IRs that already put the base first keep
    that property.
    """
    if not cad_ir.features:
        return []

    buckets: List[List[CADFeature]] = [[] for _ in _TYPE_BUCKETS]
    leftovers: List[CADFeature] = []
    for feat in cad_ir.features:
        placed = False
        for i, predicate in enumerate(_TYPE_BUCKETS):
            if predicate(feat.type):
                buckets[i].append(feat)
                placed = True
                break
        if not placed:
            leftovers.append(feat)

    # Within a bucket, keep input order (Python's sort is stable
    # when we use ``key``-less behaviour; we use explicit indices
    # below to make the intent obvious and to leave room for an
    # extra dependency pass).
    out: List[CADFeature] = []
    for bucket in buckets:
        out.extend(sorted(bucket, key=lambda f: _first_index(cad_ir.features, f)))
    out.extend(leftovers)
    return out


def _first_index(features: List[CADFeature], target: CADFeature) -> int:
    for i, f in enumerate(features):
        if f.id == target.id and f.type == target.type:
            return i
    return len(features)


def reorder_in_place(cad_ir: CADIR) -> None:
    """Replace ``cad_ir.features`` with the planned order."""
    cad_ir.features = plan_feature_sequence(cad_ir)
