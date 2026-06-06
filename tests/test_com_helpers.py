"""Unit tests for the COM bridge helpers in solidworks_com.com.

These tests do not require a running SOLIDWORKS instance. They use plain
Python objects (and ``MagicMock``) to exercise the version-drift-tolerant
property/method dispatch logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from solidworks_com.com import (
    OutCall,
    call_member,
    call_or_value,
    member_value,
    unpack_out_call,
)


@dataclass
class _FakeDispatch:
    """Stand-in for a COM dispatch object exposing ``_oleobj_``."""

    _oleobj_: int = 0


class TestCallOrValue:
    def test_returns_property_value(self) -> None:
        # No _oleobj_, not callable -> return as-is
        assert call_or_value(42) == 42
        assert call_or_value("hello") == "hello"
        assert call_or_value(None) is None

    def test_calls_no_arg_method(self) -> None:
        # A plain Python function: has no ``_oleobj_`` and is callable
        called = []

        def method() -> str:
            called.append(1)
            return "called"

        assert call_or_value(method) == "called"
        assert called == [1]

    def test_dispatch_object_not_called(self) -> None:
        dispatch = _FakeDispatch()
        # dispatch objects must not be invoked
        assert call_or_value(dispatch) is dispatch


class TestMemberValue:
    def test_reads_existing_attribute(self) -> None:
        obj = MagicMock(spec=["Title"])
        obj.Title = "Part1"
        assert member_value(obj, "Title") == "Part1"

    def test_returns_default_when_missing(self) -> None:
        obj = MagicMock(spec=[])  # no attributes
        assert member_value(obj, "Missing", default=None) is None
        assert member_value(obj, "Missing", default="fallback") == "fallback"

    def test_raises_when_missing_and_no_default(self) -> None:
        obj = MagicMock(spec=[])
        with pytest.raises(AttributeError):
            member_value(obj, "Missing")

    def test_returns_default_when_attribute_is_none(self) -> None:
        obj = MagicMock(spec=["Empty"])
        obj.Empty = None
        assert member_value(obj, "Empty", default="x") == "x"


class TestCallMember:
    def test_call_with_args(self) -> None:
        obj = MagicMock()
        obj.AddMate5 = MagicMock(return_value="mate")
        result = call_member(obj, "AddMate5", 1, 2, 3)
        assert result == "mate"
        obj.AddMate5.assert_called_once_with(1, 2, 3)

    def test_property_treated_as_value_when_no_args(self) -> None:
        obj = MagicMock(spec=["RevisionNumber"])
        obj.RevisionNumber = "33.0"
        assert call_member(obj, "RevisionNumber") == "33.0"

    def test_property_with_args_raises(self) -> None:
        obj = MagicMock(spec=["Foo"])
        obj.Foo = 42  # property, not callable
        with pytest.raises(TypeError, match="not callable"):
            call_member(obj, "Foo", 1)

    def test_default_for_missing_method(self) -> None:
        obj = MagicMock(spec=[])
        assert call_member(obj, "Nope", default="x") == "x"

    def test_missing_method_raises_without_default(self) -> None:
        obj = MagicMock(spec=[])
        with pytest.raises(AttributeError):
            call_member(obj, "Nope")


class TestUnpackOutCall:
    def test_unpacks_tuple_of_three(self) -> None:
        result = unpack_out_call(("ok", 0, 0), errors_ref=None, warnings_ref=None)
        assert result == OutCall(value="ok", errors=0, warnings=0)

    def test_unpacks_tuple_with_errors(self) -> None:
        result = unpack_out_call((None, 5, 1), errors_ref=None, warnings_ref=None)
        assert result.value is None
        assert result.errors == 5
        assert result.warnings == 1

    def test_uses_byref_when_not_tuple(self) -> None:
        result = unpack_out_call("ok", errors_ref=_ref(7), warnings_ref=_ref(2))
        assert result == OutCall(value="ok", errors=7, warnings=2)

    def test_missing_tuple_warnings(self) -> None:
        result = unpack_out_call(("ok", 3), errors_ref=None, warnings_ref=None)
        assert result.value == "ok"
        assert result.errors == 3
        assert result.warnings == 0

    def test_empty_tuple(self) -> None:
        result = unpack_out_call((), errors_ref=None, warnings_ref=None)
        assert result.value is None
        assert result.errors == 0


def _ref(value: int) -> Any:
    """Build a fake ByRef object with a .value attribute."""

    class _ByRef:
        def __init__(self, v: int) -> None:
            self.value = v

    return _ByRef(value)


class TestOutCallDataclass:
    def test_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        oc = OutCall(value=1)
        with pytest.raises(FrozenInstanceError):  # type: ignore[misc]
            oc.value = 2  # type: ignore[misc]

    def test_equality(self) -> None:
        assert OutCall(value=1, errors=2, warnings=3) == OutCall(value=1, errors=2, warnings=3)
        assert OutCall(value=1) != OutCall(value=2)
