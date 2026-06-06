"""CAD-IR -> SOLIDWORKS compiler facade.

This is the **public entry point** for the end-to-end pipeline.
It composes the three single-purpose modules:

    1. :mod:`ir_validate` -- schema-level structural checks
    2. :mod:`projection_validator` -- semantic projection checks
    3. :mod:`sw_compile` -- CAD-IR -> SW instruction stream
    4. :mod:`planner` -- feature ordering
    5. ``solidworks_com.compiler.cad_ir_to_sw`` -- SW -> COM calls

Callers may either:
    - call :func:`compile_to_solidworks` with a parsed CAD-IR dict
      and an already-connected :class:`SolidWorks` instance, or
    - call :func:`compile_only` to obtain the SW instruction
      stream dict without dispatching to SOLIDWORKS.

This module owns no geometry of its own; it is a thin orchestrator.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Make the in-tree cad_ai scripts importable.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from . import ir_schema as _schema  # noqa: E402
from . import ir_validate as _irv  # noqa: E402
from . import projection_validator as _pv  # noqa: E402
from . import sw_compile as _swc  # noqa: E402
from .schema import CADIR  # noqa: E402


def validate(cad_ir_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Run schema + projection validation.  Returns a merged result."""
    schema_result = _irv.validate_ir(cad_ir_dict)
    proj_result = _pv.validate_projection(cad_ir_dict)
    errors = list(schema_result.get("errors") or []) + list(proj_result.get("errors") or [])
    return {"ok": not errors, "errors": errors}


def compile_only(
    cad_ir_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate, then translate the IR into a SW instruction stream.

    Returns a dict with at least ``stream`` (the SW ops) on success
    and ``ok``/``errors`` always.
    """
    check = validate(cad_ir_dict)
    if not check["ok"]:
        return {"ok": False, "errors": check["errors"], "stream": None}
    try:
        stream = _swc.compile_sw(cad_ir_dict)
    except ValueError as exc:
        return {"ok": False, "errors": [{"path": "$", "code": "compile_error",
                                          "message": str(exc)}], "stream": None}
    return {"ok": True, "errors": [], "stream": stream}


def compile_to_solidworks(
    cad_ir_dict: Dict[str, Any],
    sw_app: Any,
) -> Dict[str, Any]:
    """Compile ``cad_ir_dict`` and dispatch it to ``sw_app``.

    ``sw_app`` is a connected :class:`solidworks_com.SolidWorks`
    instance (or any object that exposes ``new_part()``).

    Returns a dict ``{"ok": bool, "errors": [...], "part": modeldoc}``.
    The :class:`solidworks_com.SolidWorksError` raised by the
    dispatcher is caught and surfaced as an error rather than
    propagating -- callers should branch on ``ok``.
    """
    built = compile_only(cad_ir_dict)
    if not built["ok"]:
        return {"ok": False, "errors": built["errors"], "part": None}

    # Import the SW-side translator lazily so this module stays
    # usable even if the SW bindings are not installed.
    try:
        from solidworks_com.compiler.cad_ir_to_sw import CadIrToSw
    except ImportError as exc:
        return {"ok": False,
                "errors": [{"path": "$", "code": "translator_missing",
                            "message": str(exc)}],
                "part": None}

    part = sw_app.new_part()
    try:
        CadIrToSw(part).execute(built["stream"])
    except Exception as exc:  # noqa: BLE001 -- dispatcher is a
                              # COM call; report any failure uniformly.
        return {"ok": False,
                "errors": [{"path": "$", "code": "dispatch_error",
                            "message": str(exc)}],
                "part": part}
    return {"ok": True, "errors": [], "part": part}


# ---------- Dataclass-flavoured entry point ----------

def compile_cadir(cad_ir: CADIR, sw_app: Any) -> Dict[str, Any]:
    """Convenience: accept a :class:`CADIR` and dispatch it."""
    return compile_to_solidworks(cad_ir.to_dict(), sw_app)
