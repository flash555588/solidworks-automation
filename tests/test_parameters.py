"""Unit tests for solidworks_com.parameters."""

from __future__ import annotations

import pytest

from solidworks_com.parameters import Parameter, ParameterManager


class TestParameter:
    def test_basic_creation(self) -> None:
        p = Parameter(name="width", value=100.0, unit="mm")
        assert p.name == "width"
        assert p.value == 100.0
        assert p.unit == "mm"

    def test_update_value(self) -> None:
        p = Parameter(name="width", value=100.0)
        p.update(120.0)
        assert p.value == 120.0

    def test_min_validation(self) -> None:
        p = Parameter(name="width", value=100.0, min_value=50.0)
        p.update(30.0)
        assert p.value == 30.0  # Value is set, validation catches it
        assert len(p.validate()) == 1

    def test_max_validation(self) -> None:
        p = Parameter(name="width", value=100.0, max_value=200.0)
        p.update(300.0)
        assert p.value == 300.0  # Value is set, validation catches it
        assert len(p.validate()) == 1

    def test_observer_notified(self) -> None:
        p = Parameter(name="width", value=100.0)
        observed = []
        p.add_observer(lambda v: observed.append(v))
        p.update(120.0)
        assert observed == [120.0]

    def test_derived_parameter_cannot_update(self) -> None:
        p = Parameter(name="area", value=0.0, is_derived=True)
        with pytest.raises(ValueError, match="Cannot directly set derived"):
            p.update(100.0)

    def test_validate(self) -> None:
        p = Parameter(name="width", value=100.0, min_value=50.0, max_value=200.0)
        assert p.validate() == []

        p.value = 30.0
        assert len(p.validate()) == 1

    def test_no_change_no_notify(self) -> None:
        p = Parameter(name="width", value=100.0)
        observed = []
        p.add_observer(lambda v: observed.append(v))
        p.update(100.0)  # Same value
        assert observed == []


class TestParameterManager:
    def test_add_parameter(self) -> None:
        mgr = ParameterManager()
        p = mgr.add("width", 100.0, unit="mm")
        assert p.name == "width"
        assert "width" in mgr

    def test_duplicate_raises(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0)
        with pytest.raises(ValueError, match="already exists"):
            mgr.add("width", 50.0)

    def test_get_value(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0)
        assert mgr.get_value("width") == 100.0

    def test_update(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0)
        mgr.update("width", 120.0)
        assert mgr.get_value("width") == 120.0

    def test_add_derived(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 10.0)
        mgr.add("height", 5.0)
        mgr.add_derived("area", lambda: mgr.get_value("width") * mgr.get_value("height"))
        assert mgr.get_value("area") == 50.0

    def test_derived_updates_on_change(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 10.0)
        mgr.add("height", 5.0)
        mgr.add_derived("area", lambda: mgr.get_value("width") * mgr.get_value("height"))
        mgr.update("width", 20.0)
        assert mgr.get_value("area") == 100.0

    def test_snapshot(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0)
        mgr.add("height", 50.0)
        snap = mgr.snapshot()
        assert snap == {"width": 100.0, "height": 50.0}

    def test_apply_snapshot(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0)
        mgr.add("height", 50.0)
        mgr.apply_snapshot({"width": 200.0, "height": 75.0})
        assert mgr.get_value("width") == 200.0
        assert mgr.get_value("height") == 75.0

    def test_validate_all(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0, min_value=50.0, max_value=200.0)
        assert mgr.validate_all() == []
        mgr.update("width", 30.0)
        assert len(mgr.validate_all()) == 1

    def test_to_dict(self) -> None:
        mgr = ParameterManager()
        mgr.add("width", 100.0, unit="mm", description="Part width")
        d = mgr.to_dict()
        assert "width" in d
        assert d["width"]["value"] == 100.0
        assert d["width"]["unit"] == "mm"

    def test_len(self) -> None:
        mgr = ParameterManager()
        mgr.add("a", 1.0)
        mgr.add("b", 2.0)
        assert len(mgr) == 2

    def test_contains(self) -> None:
        mgr = ParameterManager()
        mgr.add("a", 1.0)
        assert "a" in mgr
        assert "b" not in mgr

    def test_get_missing_raises(self) -> None:
        mgr = ParameterManager()
        with pytest.raises(KeyError, match="not found"):
            mgr.get("missing")
