"""Unit tests for solidworks_com.manufacturing (no SOLIDWORKS required)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from solidworks_com.manufacturing import (
    CheckResult,
    CheckSeverity,
    ManufacturingChecker,
    ManufacturingProcess,
    ManufacturingReport,
    check_manufacturing,
)


class TestCheckResult:
    def test_to_dict_keys(self) -> None:
        r = CheckResult(
            check_name="size_limit",
            passed=True,
            severity=CheckSeverity.INFO,
            message="ok",
            process=ManufacturingProcess.CNC_MILLING,
        )
        d = r.to_dict()
        for key in ("check", "passed", "severity", "message", "process", "value", "limit"):
            assert key in d

    def test_severity_name_in_dict(self) -> None:
        r = CheckResult("x", True, CheckSeverity.WARNING, "msg")
        assert r.to_dict()["severity"] == "WARNING"

    def test_process_none_allowed(self) -> None:
        r = CheckResult("x", True, CheckSeverity.INFO, "msg", process=None)
        assert r.to_dict()["process"] is None


class TestManufacturingReport:
    def _make_report(self) -> ManufacturingReport:
        report = ManufacturingReport(model_name="part", process=ManufacturingProcess.FDM_PRINTING)
        report.add_result(CheckResult("c1", True, CheckSeverity.INFO, "passed"))
        report.add_result(CheckResult("c2", False, CheckSeverity.ERROR, "failed"))
        report.add_result(CheckResult("c3", False, CheckSeverity.WARNING, "warn"))
        return report

    def test_success_false_when_errors(self) -> None:
        assert self._make_report().success is False

    def test_success_true_when_no_errors(self) -> None:
        report = ManufacturingReport(model_name="p", process=ManufacturingProcess.CNC_MILLING)
        report.add_result(CheckResult("c1", True, CheckSeverity.INFO, "ok"))
        assert report.success is True

    def test_total_checks_count(self) -> None:
        assert self._make_report().total_checks == 3

    def test_passed_checks_count(self) -> None:
        assert self._make_report().passed_checks == 1

    def test_error_count(self) -> None:
        assert self._make_report().errors == 1

    def test_warning_count(self) -> None:
        assert self._make_report().warnings == 1

    def test_to_dict_structure(self) -> None:
        d = self._make_report().to_dict()
        assert "model" in d
        assert "process" in d
        assert "results" in d
        assert "summary" in d
        assert d["summary"]["total"] == 3

    def test_summary_string(self) -> None:
        s = self._make_report().summary()
        assert "Manufacturing Report" in s
        assert "FDM_PRINTING" in s


class TestManufacturingChecker:
    def _make_model(self, size=None) -> MagicMock:
        model = MagicMock()
        model.title = "part"
        model.safe_size.return_value = size
        return model

    def test_cnc_milling_returns_report(self) -> None:
        checker = ManufacturingChecker(self._make_model())
        report = checker.check(ManufacturingProcess.CNC_MILLING)
        assert isinstance(report, ManufacturingReport)
        assert report.total_checks > 0

    def test_fdm_returns_report(self) -> None:
        checker = ManufacturingChecker(self._make_model())
        report = checker.check(ManufacturingProcess.FDM_PRINTING)
        assert isinstance(report, ManufacturingReport)

    def test_laser_cutting_returns_report(self) -> None:
        checker = ManufacturingChecker(self._make_model())
        report = checker.check(ManufacturingProcess.LASER_CUTTING)
        assert isinstance(report, ManufacturingReport)

    def test_generic_process_returns_report(self) -> None:
        checker = ManufacturingChecker(self._make_model())
        report = checker.check(ManufacturingProcess.SLS_PRINTING)
        assert isinstance(report, ManufacturingReport)

    def test_large_part_warns_cnc(self) -> None:
        checker = ManufacturingChecker(self._make_model(size=(2.0, 2.0, 2.0)))
        report = checker.check(ManufacturingProcess.CNC_MILLING)
        size_check = next(r for r in report.results if r.check_name == "size_limit")
        assert not size_check.passed

    def test_small_part_passes_cnc(self) -> None:
        checker = ManufacturingChecker(self._make_model(size=(0.1, 0.1, 0.1)))
        report = checker.check(ManufacturingProcess.CNC_MILLING)
        size_check = next(r for r in report.results if r.check_name == "size_limit")
        assert size_check.passed

    def test_large_part_warns_fdm(self) -> None:
        checker = ManufacturingChecker(self._make_model(size=(0.5, 0.5, 0.5)))
        report = checker.check(ManufacturingProcess.FDM_PRINTING)
        printer_check = next((r for r in report.results if r.check_name == "printer_size"), None)
        assert printer_check is not None
        assert not printer_check.passed

    def test_thick_part_warns_laser(self) -> None:
        checker = ManufacturingChecker(self._make_model(size=(0.5, 0.3, 0.1)))
        report = checker.check(ManufacturingProcess.LASER_CUTTING)
        thick_check = next((r for r in report.results if r.check_name == "thickness"), None)
        assert thick_check is not None
        assert not thick_check.passed

    def test_no_bbox_skips_size_checks(self) -> None:
        checker = ManufacturingChecker(self._make_model(size=None))
        report = checker.check(ManufacturingProcess.CNC_MILLING)
        assert isinstance(report, ManufacturingReport)


class TestCheckManufacturing:
    def test_convenience_function(self) -> None:
        model = MagicMock()
        model.title = "part"
        model.safe_size.return_value = None
        report = check_manufacturing(model, ManufacturingProcess.FDM_PRINTING)
        assert isinstance(report, ManufacturingReport)
