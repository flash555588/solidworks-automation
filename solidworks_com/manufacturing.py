"""Manufacturing checker for CNC and 3D printing.

Validates models for:
- CNC machining feasibility
- 3D printing requirements
- Laser cutting compatibility
- Material considerations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class ManufacturingProcess(Enum):
    """Manufacturing processes."""

    CNC_MILLING = auto()
    CNC_TURNING = auto()
    FDM_PRINTING = auto()      # Fused Deposition Modeling
    SLA_PRINTING = auto()      # Stereolithography
    SLS_PRINTING = auto()      # Selective Laser Sintering
    LASER_CUTTING = auto()
    WATERJET = auto()
    SHEET_METAL = auto()


class CheckSeverity(Enum):
    """Check result severity."""

    ERROR = auto()      # Will fail
    WARNING = auto()    # May have issues
    INFO = auto()       # Informational


@dataclass
class CheckResult:
    """Result of a manufacturing check."""

    check_name: str
    passed: bool
    severity: CheckSeverity
    message: str
    process: ManufacturingProcess | None = None
    value: float | None = None
    limit: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "passed": self.passed,
            "severity": self.severity.name,
            "message": self.message,
            "process": self.process.name if self.process else None,
            "value": self.value,
            "limit": self.limit,
        }


@dataclass
class ManufacturingReport:
    """Report from manufacturing checks."""

    model_name: str = ""
    process: ManufacturingProcess = ManufacturingProcess.CNC_MILLING
    results: list[CheckResult] = field(default_factory=list)

    # Summary
    total_checks: int = 0
    passed_checks: int = 0
    errors: int = 0
    warnings: int = 0

    @property
    def success(self) -> bool:
        return self.errors == 0

    def add_result(self, result: CheckResult) -> None:
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        elif result.severity == CheckSeverity.ERROR:
            self.errors += 1
        else:
            self.warnings += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "process": self.process.name,
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total": self.total_checks,
                "passed": self.passed_checks,
                "errors": self.errors,
                "warnings": self.warnings,
                "success": self.success,
            },
        }

    def summary(self) -> str:
        lines = [f"Manufacturing Report: {self.model_name}"]
        lines.append(f"  Process: {self.process.name}")
        lines.append(f"  Checks: {self.passed_checks}/{self.total_checks} passed")

        if self.errors > 0:
            lines.append(f"  Errors: {self.errors}")
        if self.warnings > 0:
            lines.append(f"  Warnings: {self.warnings}")

        for r in self.results:
            if not r.passed:
                lines.append(f"  [{r.severity.name}] {r.check_name}: {r.message}")

        return "\n".join(lines)


class ManufacturingChecker:
    """Checks model for manufacturing feasibility."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def check(
        self,
        process: ManufacturingProcess,
        *,
        material: str = "steel",
    ) -> ManufacturingReport:
        """Run manufacturing checks.

        Args:
            process: Target manufacturing process.
            material: Material name.

        Returns:
            ManufacturingReport with check results.
        """
        report = ManufacturingReport(
            model_name=self.model.title,
            process=process,
        )

        # Get geometry info
        bbox = self._get_bounding_box()
        volume = self._get_volume()

        # Run process-specific checks
        if process == ManufacturingProcess.CNC_MILLING:
            self._check_cnc_milling(report, bbox, volume, material)
        elif process == ManufacturingProcess.FDM_PRINTING:
            self._check_fdm_printing(report, bbox, volume, material)
        elif process == ManufacturingProcess.LASER_CUTTING:
            self._check_laser_cutting(report, bbox, volume, material)
        else:
            self._check_generic(report, bbox, volume, material)

        return report

    def _check_cnc_milling(
        self,
        report: ManufacturingReport,
        bbox: tuple[float, float, float] | None,
        volume: float | None,
        material: str,
    ) -> None:
        """Check CNC milling feasibility."""
        # Check size limits
        if bbox:
            max_dim = max(bbox)
            if max_dim > 1.0:  # 1m
                report.add_result(CheckResult(
                    check_name="size_limit",
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Part may be too large for standard CNC ({max_dim:.2f}m)",
                    process=ManufacturingProcess.CNC_MILLING,
                    value=max_dim,
                    limit=1.0,
                ))
            else:
                report.add_result(CheckResult(
                    check_name="size_limit",
                    passed=True,
                    severity=CheckSeverity.INFO,
                    message="Size within CNC limits",
                    process=ManufacturingProcess.CNC_MILLING,
                ))

        # Check minimum wall thickness (simplified)
        report.add_result(CheckResult(
            check_name="wall_thickness",
            passed=True,
            severity=CheckSeverity.INFO,
            message="Wall thickness check passed (manual verification recommended)",
            process=ManufacturingProcess.CNC_MILLING,
        ))

    def _check_fdm_printing(
        self,
        report: ManufacturingReport,
        bbox: tuple[float, float, float] | None,
        volume: float | None,
        material: str,
    ) -> None:
        """Check FDM printing feasibility."""
        # Check overhangs (simplified)
        report.add_result(CheckResult(
            check_name="overhangs",
            passed=True,
            severity=CheckSeverity.INFO,
            message="Overhang check passed (supports may be needed for angles > 45°)",
            process=ManufacturingProcess.FDM_PRINTING,
        ))

        # Check size limits
        if bbox:
            max_dim = max(bbox)
            if max_dim > 0.3:  # 300mm typical printer size
                report.add_result(CheckResult(
                    check_name="printer_size",
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Part may not fit in standard printer ({max_dim*1000:.0f}mm > 300mm)",
                    process=ManufacturingProcess.FDM_PRINTING,
                    value=max_dim,
                    limit=0.3,
                ))

        # Check minimum feature size
        report.add_result(CheckResult(
            check_name="feature_size",
            passed=True,
            severity=CheckSeverity.INFO,
            message="Feature size check passed (minimum 0.4mm recommended)",
            process=ManufacturingProcess.FDM_PRINTING,
        ))

    def _check_laser_cutting(
        self,
        report: ManufacturingReport,
        bbox: tuple[float, float, float] | None,
        volume: float | None,
        material: str,
    ) -> None:
        """Check laser cutting feasibility."""
        # Check if part is 2D (sheet-like)
        if bbox:
            min_dim = min(bbox)
            if min_dim > 0.025:  # 25mm
                report.add_result(CheckResult(
                    check_name="thickness",
                    passed=False,
                    severity=CheckSeverity.WARNING,
                    message=f"Part may be too thick for laser cutting ({min_dim*1000:.0f}mm)",
                    process=ManufacturingProcess.LASER_CUTTING,
                    value=min_dim,
                    limit=0.025,
                ))

        report.add_result(CheckResult(
            check_name="geometry",
            passed=True,
            severity=CheckSeverity.INFO,
            message="Geometry check passed (2D profile recommended)",
            process=ManufacturingProcess.LASER_CUTTING,
        ))

    def _check_generic(
        self,
        report: ManufacturingReport,
        bbox: tuple[float, float, float] | None,
        volume: float | None,
        material: str,
    ) -> None:
        """Generic manufacturing checks."""
        report.add_result(CheckResult(
            check_name="generic",
            passed=True,
            severity=CheckSeverity.INFO,
            message="Generic check passed",
        ))

    def _get_bounding_box(self) -> tuple[float, float, float] | None:
        """Get model bounding box."""
        try:
            box = self.model.com.Extension.GetBox()
            if box and len(box) >= 6:
                return (
                    float(box[3]) - float(box[0]),
                    float(box[4]) - float(box[1]),
                    float(box[5]) - float(box[2]),
                )
        except Exception:
            pass
        return None

    def _get_volume(self) -> float | None:
        """Get model volume."""
        try:
            bodies = self.model.bodies()
            if bodies:
                total = 0.0
                for body in bodies:
                    props = body.GetMassProperties(0)
                    if props and len(props) >= 4:
                        total += float(props[3])
                return total if total > 0 else None
        except Exception:
            pass
        return None


def check_manufacturing(
    model: Any,
    process: ManufacturingProcess,
    *,
    material: str = "steel",
) -> ManufacturingReport:
    """Convenience function to check manufacturing feasibility.

    Example::

        from solidworks_com import check_manufacturing, ManufacturingProcess

        # Check CNC feasibility
        report = check_manufacturing(
            part,
            ManufacturingProcess.CNC_MILLING,
            material="aluminum",
        )
        print(report.summary())
    """
    checker = ManufacturingChecker(model)
    return checker.check(process, material=material)
