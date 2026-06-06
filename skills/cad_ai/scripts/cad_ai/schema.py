"""CAD-IR schema as Python dataclasses (facade over JSON dict).

The canonical CAD-IR v0 is a JSON document walked by
``ir_schema.py`` and ``ir_validate.py`` (deliberately
std-library-only).  This module offers an optional **Python
dataclass** facade so callers can build IR programmatically and
serialise to / from JSON without losing the v0 contract.

Every dataclass here round-trips through the JSON form via
:meth:`to_dict` / :meth:`from_dict`.  Validation in the canonical
sense still flows through ``ir_validate.validate_ir``; this module
is a typed convenience layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

Number = Union[int, float]
ParamRef = Union[Number, str]  # number literal or parameter name


@dataclass
class CADParameter:
    """A named numeric or symbolic parameter.

    The dataclass form is the convenience API; the canonical v0
    IR keeps parameters as a flat ``{name: value}`` mapping, with
    the unit on the top-level ``units`` field.
    """

    name: str
    value: Union[Number, str]
    unit: str = "mm"

    def to_dict(self) -> Dict[str, Any]:
        return {self.name: self.value}


@dataclass
class CADFeature:
    """A single geometric feature (extrude, cut, fillet, ...).

    On the dataclass side the top-level fields are limited to
    ``id``, ``type``, and ``references``; everything else
    (``sketch``, ``depth``, ``direction``, ``target``,
    ``selector``, ...) lives inside ``parameters``.  This mirrors
    how the JSON form looks while keeping the dataclass simple.
    """

    id: str
    type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id, "type": self.type}
        out.update(self.parameters)
        if self.references:
            out["references"] = list(self.references)
        return out


@dataclass
class CADIR:
    """A complete CAD-IR document (v0 schema).

    ``parameters`` is a flat ``{name: number-or-string-ref}`` map.
    ``features`` are ordered; downstream compilers are responsible
    for any further ordering (see :mod:`planner`).
    """

    name: str
    units: str = "mm"
    parameters: Dict[str, Union[Number, str]] = field(default_factory=dict)
    features: List[CADFeature] = field(default_factory=list)
    document_type: str = "part"
    up_axis: str = "Z"
    front_axis: str = "Y"
    origin: str = "part_center"
    acceptance: Optional[Dict[str, Any]] = None

    # ---------- Serialisation ----------

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema": "cad_ir.v0",
            "units": self.units,
            "document": {"type": self.document_type, "name": self.name},
            "coordinate_system": {
                "origin": self.origin,
                "up_axis": self.up_axis,
                "front_axis": self.front_axis,
            },
            "parameters": dict(self.parameters),
            "features": [f.to_dict() for f in self.features],
        }
        if self.acceptance is not None:
            out["acceptance"] = dict(self.acceptance)
        return out

    @classmethod
    def from_dict(cls, doc: Dict[str, Any]) -> "CADIR":
        """Build a CADIR from a canonical v0 dict (e.g. parsed JSON)."""
        if not isinstance(doc, dict):
            raise TypeError(
                f"CADIR.from_dict expected dict, got {type(doc).__name__}"
            )
        doc_obj = doc.get("document", {}) or {}
        cs = doc.get("coordinate_system", {}) or {}
        params: Dict[str, Union[Number, str]] = {}
        for k, v in (doc.get("parameters") or {}).items():
            params[k] = v
        feats: List[CADFeature] = []
        for f in (doc.get("features") or []):
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            ftype = f.get("type")
            if not fid or not ftype:
                # Skip malformed features silently; the validator
                # emits a structured error if validation runs.
                continue
            # The v0 IR feature dict carries its own per-type
            # fields (``sketch``, ``depth``, ``direction``,
            # ``target``, ``selector``, ...).  On the dataclass
            # side those all live inside ``parameters``; the
            # top-level fields are limited to ``id``, ``type``,
            # and (optionally) ``references``.  We shuffle
            # per-type fields into ``parameters`` here so the
            # round-trip is faithful and ``CADFeature(**...)``
            # does not blow up.
            params_for_feat: Dict[str, Any] = {}
            for k, v in f.items():
                if k in ("id", "type", "references"):
                    continue
                params_for_feat[k] = v
            kwargs: Dict[str, Any] = {
                "id": fid, "type": ftype,
                "parameters": params_for_feat,
            }
            refs = f.get("references")
            if refs:
                kwargs["references"] = list(refs)
            feats.append(CADFeature(**kwargs))
        return cls(
            name=str(doc_obj.get("name", "part")),
            units=str(doc.get("units", "mm")),
            parameters=params,
            features=feats,
            document_type=str(doc_obj.get("type", "part")),
            up_axis=str(cs.get("up_axis", "Z")),
            front_axis=str(cs.get("front_axis", "Y")),
            origin=str(cs.get("origin", "part_center")),
            acceptance=doc.get("acceptance"),
        )

    def to_json(self) -> str:
        """Serialise to canonical v0 JSON text."""
        import json
        return json.dumps(self.to_dict(), indent=2)

    # ---------- Convenience ----------

    def add_feature(self, feature: CADFeature) -> None:
        self.features.append(feature)

    def add_parameter(self, name: str, value: Union[Number, str]) -> None:
        self.parameters[name] = value

    def feature_by_id(self, fid: str) -> Optional[CADFeature]:
        for f in self.features:
            if f.id == fid:
                return f
        return None
