"""Parameter management for SOLIDWORKS models.

Inspired by text-to-cad's parameter design principles:
- Parameters are part of the model contract
- Named parameters with clear intent
- Derive dependent values from constraints
- Validate parameter behavior at representative values
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Parameter:
    """A named model parameter with metadata and validation."""

    name: str
    value: float
    unit: str = "mm"
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    is_derived: bool = False
    derivation_fn: Callable[[], float] | None = None
    _observers: list[Callable[[float], None]] = field(default_factory=list)

    def update(self, new_value: float) -> None:
        """Update parameter value and notify observers."""
        if self.is_derived:
            raise ValueError(f"Cannot directly set derived parameter '{self.name}'")
        old_value = self.value
        self.value = new_value
        if old_value != new_value:
            for observer in self._observers:
                observer(new_value)

    def add_observer(self, callback: Callable[[float], None]) -> None:
        """Add an observer to be notified when value changes."""
        self._observers.append(callback)

    def validate(self) -> list[str]:
        """Validate parameter value and return list of issues."""
        issues = []
        if self.min_value is not None and self.value < self.min_value:
            issues.append(f"{self.name}: {self.value} < min {self.min_value}")
        if self.max_value is not None and self.value > self.max_value:
            issues.append(f"{self.name}: {self.value} > max {self.max_value}")
        return issues


class ParameterManager:
    """Manages a collection of model parameters with dependency tracking."""

    def __init__(self) -> None:
        self._parameters: dict[str, Parameter] = {}
        self._derived_order: list[str] = []

    def add(
        self,
        name: str,
        value: float,
        *,
        unit: str = "mm",
        description: str = "",
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> Parameter:
        """Add a new parameter."""
        if name in self._parameters:
            raise ValueError(f"Parameter '{name}' already exists")
        param = Parameter(
            name=name,
            value=value,
            unit=unit,
            description=description,
            min_value=min_value,
            max_value=max_value,
        )
        self._parameters[name] = param
        return param

    def add_derived(
        self,
        name: str,
        derivation_fn: Callable[[], float],
        *,
        unit: str = "mm",
        description: str = "",
    ) -> Parameter:
        """Add a derived parameter that computes its value from other parameters."""
        if name in self._parameters:
            raise ValueError(f"Parameter '{name}' already exists")
        param = Parameter(
            name=name,
            value=0.0,  # Will be computed
            unit=unit,
            description=description,
            is_derived=True,
            derivation_fn=derivation_fn,
        )
        self._parameters[name] = param
        self._derived_order.append(name)
        # Compute initial value
        param.value = derivation_fn()
        return param

    def get(self, name: str) -> Parameter:
        """Get a parameter by name."""
        if name not in self._parameters:
            raise KeyError(f"Parameter '{name}' not found")
        return self._parameters[name]

    def get_value(self, name: str) -> float:
        """Get parameter value by name."""
        return self.get(name).value

    def update(self, name: str, value: float) -> None:
        """Update a parameter value."""
        self.get(name).update(value)
        self._update_derived()

    def _update_derived(self) -> None:
        """Update all derived parameters in dependency order."""
        for name in self._derived_order:
            param = self._parameters[name]
            if param.derivation_fn:
                param.value = param.derivation_fn()

    def validate_all(self) -> list[str]:
        """Validate all parameters and return list of issues."""
        issues = []
        for param in self._parameters.values():
            issues.extend(param.validate())
        return issues

    def snapshot(self) -> dict[str, float]:
        """Get a snapshot of all parameter values."""
        return {name: param.value for name, param in self._parameters.items()}

    def apply_snapshot(self, snapshot: dict[str, float]) -> None:
        """Apply a parameter snapshot."""
        for name, value in snapshot.items():
            if name in self._parameters and not self._parameters[name].is_derived:
                self._parameters[name].value = value
        self._update_derived()

    def to_dict(self) -> dict[str, Any]:
        """Export parameters as dictionary."""
        return {
            name: {
                "value": param.value,
                "unit": param.unit,
                "description": param.description,
                "is_derived": param.is_derived,
                "min": param.min_value,
                "max": param.max_value,
            }
            for name, param in self._parameters.items()
        }

    def __contains__(self, name: str) -> bool:
        return name in self._parameters

    def __iter__(self):
        return iter(self._parameters.values())

    def __len__(self) -> int:
        return len(self._parameters)
