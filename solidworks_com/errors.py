"""Error types for solidworks_com.

``SolidWorksError`` carries not just a message but the COM method name and
positional arguments that triggered the failure, plus the raw COM exception
when one was caught. This makes debugging much cheaper when a long call
chain breaks deep inside the wrapper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    errors: int = 0
    warnings: int = 0


class SolidWorksError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        errors: int = 0,
        warnings: int = 0,
        method: str | None = None,
        args: Sequence[Any] | None = None,
        com_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = errors
        self.warnings = warnings
        # ``method`` is the COM member that failed (e.g. ``IModelDoc2.Save3``).
        self.method = method
        # ``args_payload`` is the positional argument tuple at the time of the
        # failure, truncated to a reasonable size when rendering.
        self.args_payload: tuple[Any, ...] | None = tuple(args) if args is not None else None
        # ``com_error`` is the original COM exception when one was caught.
        self.com_error = com_error

    def __str__(self) -> str:
        head = super().__str__()
        details: list[str] = []
        if self.errors:
            details.append(f"errors={self.errors}")
        if self.warnings:
            details.append(f"warnings={self.warnings}")
        if self.method:
            details.append(f"method={self.method}")
        if self.args_payload:
            rendered = ", ".join(_render_arg(a) for a in self.args_payload)
            details.append(f"args=({rendered})")
        if self.com_error is not None:
            details.append(f"com_error={type(self.com_error).__name__}: {self.com_error}")
        if not details:
            return head
        return f"{head} ({', '.join(details)})"


def _render_arg(arg: Any) -> str:
    """Render a single COM argument for inclusion in an error message."""
    s = repr(arg)
    if len(s) > 120:
        s = s[:117] + "..."
    return s
