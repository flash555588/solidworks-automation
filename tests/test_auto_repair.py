"""Unit tests for auto repair module."""

from __future__ import annotations

from solidworks_com.auto_repair import (
    AutoRepairLoop,
    RepairAction,
    RepairAttempt,
    RepairReport,
    execute_with_repair,
)


class TestRepairAction:
    def test_values(self) -> None:
        assert RepairAction.RETRY.name == "RETRY"
        assert RepairAction.ROLLBACK.name == "ROLLBACK"
        assert RepairAction.ABORT.name == "ABORT"


class TestRepairAttempt:
    def test_creation(self) -> None:
        a = RepairAttempt(
            action=RepairAction.RETRY,
            description="Test",
            success=True,
        )
        assert a.success is True
        assert a.error is None

    def test_to_dict(self) -> None:
        a = RepairAttempt(
            action=RepairAction.RETRY,
            description="Test",
            success=False,
            error="Failed",
        )
        d = a.to_dict()
        assert d["action"] == "RETRY"
        assert d["success"] is False
        assert d["error"] == "Failed"


class TestRepairReport:
    def test_creation(self) -> None:
        r = RepairReport(operation="Test")
        assert r.operation == "Test"
        assert r.total_attempts == 0

    def test_add_attempt(self) -> None:
        r = RepairReport(operation="Test")
        r.add_attempt(RepairAttempt(
            action=RepairAction.RETRY,
            description="Attempt 1",
            success=True,
        ))
        assert r.total_attempts == 1

    def test_summary(self) -> None:
        r = RepairReport(operation="Test")
        r.add_attempt(RepairAttempt(
            action=RepairAction.RETRY,
            description="Attempt 1",
            success=True,
        ))
        r.final_success = True
        s = r.summary()
        assert "Test" in s
        assert "SUCCESS" in s

    def test_to_dict(self) -> None:
        r = RepairReport(operation="Test")
        d = r.to_dict()
        assert d["operation"] == "Test"
        assert "attempts" in d


class TestAutoRepairLoop:
    def test_creation(self) -> None:
        loop = AutoRepairLoop(None)
        assert loop.max_retries == 3

    def test_execute_success(self) -> None:
        loop = AutoRepairLoop(None)

        def success_op():
            return True

        success, report = loop.execute_with_repair("Test", success_op)
        assert success is True
        assert report.final_success is True

    def test_execute_with_fix(self) -> None:
        loop = AutoRepairLoop(None)
        attempt = [0]

        def failing_op():
            attempt[0] += 1
            if attempt[0] < 2:
                raise ValueError("First attempt fails")
            return True

        def fix():
            return True

        success, report = loop.execute_with_repair(
            "Test",
            failing_op,
            fix_attempts=[fix],
        )
        assert success is True
        assert report.total_attempts > 1

    def test_execute_all_fail(self) -> None:
        loop = AutoRepairLoop(None)

        def always_fail():
            raise ValueError("Always fails")

        success, report = loop.execute_with_repair("Test", always_fail)
        assert success is False
        assert report.final_success is False


class TestExecuteWithRepair:
    def test_success(self) -> None:
        def success_op():
            return True

        success, report = execute_with_repair(None, "Test", success_op)
        assert success is True

    def test_failure(self) -> None:
        def fail_op():
            raise ValueError("Failed")

        success, report = execute_with_repair(None, "Test", fail_op)
        assert success is False
