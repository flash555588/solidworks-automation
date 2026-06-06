from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

_pythoncom: Any = None
_win32com_client: Any = None


def import_pywin32() -> tuple[Any, Any]:
    """Return (pythoncom, win32com.client), importing and caching on first call."""
    global _pythoncom, _win32com_client
    if _pythoncom is None or _win32com_client is None:
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            if sys.platform == "win32":
                raise RuntimeError("solidworks-com requires pywin32 on Windows. Install with: pip install pywin32") from exc
            _pythoncom = SimpleNamespace(
                VT_BYREF=0x4000,
                VT_I4=3,
                VT_DISPATCH=9,
                VT_EMPTY=0,
                VT_VARIANT=12,
                VT_ARRAY=0x2000,
                VT_R8=5,
            )
            _win32com_client = SimpleNamespace(VARIANT=lambda variant_type, value: (variant_type, value))
        else:
            _pythoncom = pythoncom
            _win32com_client = win32com.client
    return _pythoncom, _win32com_client


def int_byref() -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def empty_dispatch() -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_DISPATCH, None)


def empty_variant() -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_EMPTY, None)


def variant_byref() -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)


def double_array(values: list[float] | tuple[float, ...]) -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(value) for value in values])


def variant_array(values: list[Any] | tuple[Any, ...]) -> Any:
    pythoncom, win32com_client = import_pywin32()
    return win32com_client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, list(values))


_MISSING = object()


def call_or_value(member: Any) -> Any:
    """Return a COM property value, or call a no-argument COM method.

    pywin32 dynamic dispatch and makepy-generated wrappers do not always expose
    SOLIDWORKS members in the same shape. APIs documented as no-argument
    methods, such as GetTitle, can appear as already-evaluated properties on
    some machines. Dispatch objects themselves may also be callable-looking in
    ways we should not invoke accidentally, so keep them as values.
    """
    if hasattr(member, "_oleobj_"):
        return member
    return member() if callable(member) else member


def member_value(obj: Any, name: str, default: Any = _MISSING) -> Any:
    try:
        member = getattr(obj, name)
    except AttributeError:
        if default is _MISSING:
            raise
        return default
    if member is None:
        return default if default is not _MISSING else None
    return call_or_value(member)


def call_member(obj: Any, name: str, *args: Any, default: Any = _MISSING) -> Any:
    """Call a COM member while tolerating no-argument method/property drift.

    Use this for members documented as methods. When arguments are supplied the
    member must be callable; when no arguments are supplied, a pre-evaluated
    property value is accepted. This keeps accidental calls to property values
    from producing opaque errors like "'bool' object is not callable".
    """
    try:
        member = getattr(obj, name)
    except AttributeError:
        if default is _MISSING:
            raise
        return default
    if callable(member):
        return member(*args)
    if args:
        if default is not _MISSING:
            return default
        raise TypeError(f"COM member {name} is not callable")
    return member


@dataclass(frozen=True)
class OutCall:
    value: Any
    errors: int = 0
    warnings: int = 0


def unpack_out_call(result: Any, errors_ref: Any, warnings_ref: Any) -> OutCall:
    if isinstance(result, tuple):
        value = result[0] if result else None
        errors = int(result[1]) if len(result) > 1 and result[1] is not None else 0
        warnings = int(result[2]) if len(result) > 2 and result[2] is not None else 0
        return OutCall(value, errors, warnings)
    return OutCall(result, int(getattr(errors_ref, "value", 0) or 0), int(getattr(warnings_ref, "value", 0) or 0))
