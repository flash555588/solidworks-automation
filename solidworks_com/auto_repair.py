"""Auto-repair loop for CAD modeling operations.

Inspired by text-to-cad's repair-loop principles:
- Attempt minimal fixes before giving up
- Roll back to last successful state
- Retry with modified parameters
- Only exit when all options exhausted
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RepairAction(Enum):
    """Actions to take when an error occurs."""

    RETRY = auto()           # Retry the same operation
    ROLLBACK = auto()        # Roll back to previous state
    MODIFY_PARAMS = auto()   # Modify parameters and retry
    SKIP = auto()            # Skip this step
    ABORT = auto()           # Abort and start fresh


@dataclass
class RepairAttempt:
    """Record of a repair attempt."""

    action: RepairAction
    description: str
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.name,
            "description": self.description,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class RepairReport:
    """Report from repair loop."""

    operation: str
    attempts: list[RepairAttempt] = field(default_factory=list)
    final_success: bool = False
    total_attempts: int = 0

    def add_attempt(self, attempt: RepairAttempt) -> None:
        self.attempts.append(attempt)
        self.total_attempts += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "attempts": [a.to_dict() for a in self.attempts],
            "finalSuccess": self.final_success,
            "totalAttempts": self.total_attempts,
        }

    def summary(self) -> str:
        lines = [f"Repair Report: {self.operation}"]
        lines.append(f"  Total attempts: {self.total_attempts}")
        lines.append(f"  Final result: {'SUCCESS' if self.final_success else 'FAILED'}")

        for i, attempt in enumerate(self.attempts, 1):
            status = "✓" if attempt.success else "✗"
            lines.append(f"  {i}. [{status}] {attempt.action.name}: {attempt.description}")
            if attempt.error:
                lines.append(f"     Error: {attempt.error}")

        return "\n".join(lines)


class AutoRepairLoop:
    """Automatic repair loop for CAD operations.

    Attempts to fix errors automatically before giving up.
    """

    def __init__(
        self,
        model: Any,
        *,
        max_retries: int = 3,
        max_rollbacks: int = 2,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.max_rollbacks = max_rollbacks
        self._snapshots: list[dict[str, Any]] = []
        self._current_snapshot: int = -1

    def take_snapshot(self) -> int:
        """Take a snapshot of current model state."""
        snapshot_id = len(self._snapshots)
        snapshot = {
            "id": snapshot_id,
            "feature_count": self._get_feature_count(),
            "body_count": self._get_body_count(),
        }
        self._snapshots.append(snapshot)
        self._current_snapshot = snapshot_id
        logger.debug("Snapshot %d taken", snapshot_id)
        return snapshot_id

    def execute_with_repair(
        self,
        operation_name: str,
        operation: Callable[[], Any],
        *,
        fix_attempts: list[Callable[[], bool]] | None = None,
    ) -> tuple[bool, RepairReport]:
        """Execute an operation with automatic repair on failure.

        Args:
            operation_name: Name of the operation for logging.
            operation: The operation to execute.
            fix_attempts: Optional list of fix functions to try.

        Returns:
            Tuple of (success, report).
        """
        report = RepairReport(operation=operation_name)

        # Take snapshot before operation
        self.take_snapshot()

        # Try the operation
        try:
            operation()
            report.add_attempt(RepairAttempt(
                action=RepairAction.RETRY,
                description="Initial attempt",
                success=True,
            ))
            report.final_success = True
            return True, report
        except Exception as e:
            initial_error = str(e)
            logger.warning("Operation '%s' failed: %s", operation_name, initial_error)
            report.add_attempt(RepairAttempt(
                action=RepairAction.RETRY,
                description="Initial attempt",
                success=False,
                error=initial_error,
            ))

        # Try fix attempts
        if fix_attempts:
            for i, fix_fn in enumerate(fix_attempts):
                if i >= self.max_retries:
                    break

                logger.info("Trying fix attempt %d...", i + 1)
                try:
                    fix_success = fix_fn()
                    report.add_attempt(RepairAttempt(
                        action=RepairAction.MODIFY_PARAMS,
                        description=f"Fix attempt {i+1}",
                        success=fix_success,
                    ))

                    if fix_success:
                        # Retry operation after fix
                        try:
                            operation()
                            report.add_attempt(RepairAttempt(
                                action=RepairAction.RETRY,
                                description=f"Retry after fix {i+1}",
                                success=True,
                            ))
                            report.final_success = True
                            return True, report
                        except Exception as e:
                            report.add_attempt(RepairAttempt(
                                action=RepairAction.RETRY,
                                description=f"Retry after fix {i+1}",
                                success=False,
                                error=str(e),
                            ))
                except Exception as e:
                    report.add_attempt(RepairAttempt(
                        action=RepairAction.MODIFY_PARAMS,
                        description=f"Fix attempt {i+1}",
                        success=False,
                        error=str(e),
                    ))

        # Try rollback
        if self._current_snapshot > 0:
            logger.info("Attempting rollback...")
            try:
                self._rollback()
                report.add_attempt(RepairAttempt(
                    action=RepairAction.ROLLBACK,
                    description="Rollback to previous snapshot",
                    success=True,
                ))

                # Retry operation after rollback
                try:
                    operation()
                    report.add_attempt(RepairAttempt(
                        action=RepairAction.RETRY,
                        description="Retry after rollback",
                        success=True,
                    ))
                    report.final_success = True
                    return True, report
                except Exception as e:
                    report.add_attempt(RepairAttempt(
                        action=RepairAction.RETRY,
                        description="Retry after rollback",
                        success=False,
                        error=str(e),
                    ))
            except Exception as e:
                report.add_attempt(RepairAttempt(
                    action=RepairAction.ROLLBACK,
                    description="Rollback failed",
                    success=False,
                    error=str(e),
                ))

        # All attempts failed
        report.final_success = False
        return False, report

    def _rollback(self) -> None:
        """Rollback to previous snapshot.

        .. note::
            True rollback requires the SOLIDWORKS ``EditUndo2`` API or a
            ``MoveRollbackBarTo`` call. ``take_snapshot`` only records counts
            (feature_count, body_count), not actual model state, so restoring
            from a snapshot is not possible without additional implementation.
        """
        raise NotImplementedError(
            "AutoRepairLoop._rollback is not implemented. "
            "Use model.com.EditUndo2(n) or IFeatureManager.EditRollback to restore state."
        )

    def _get_feature_count(self) -> int:
        """Get current feature count."""
        try:
            features = list(self.model.iter_features())
            return len(features)
        except (AttributeError, TypeError) as e:
            logger.debug("_get_feature_count failed: %s", e)
            return 0

    def _get_body_count(self) -> int:
        """Get current body count."""
        try:
            bodies = self.model.bodies()
            return len(bodies) if bodies else 0
        except (AttributeError, TypeError) as e:
            logger.debug("_get_body_count failed: %s", e)
            return 0


def execute_with_repair(
    model: Any,
    operation_name: str,
    operation: Callable[[], Any],
    *,
    max_retries: int = 3,
    fix_attempts: list[Callable[[], bool]] | None = None,
) -> tuple[bool, RepairReport]:
    """Convenience function to execute with auto-repair.

    Example::

        from solidworks_com import execute_with_repair

        def create_slot():
            part.select_plane("Front Plane")
            with part.sketch() as sk:
                sk.line(-10, 10, 0, 10, 10, 0)
                sk.line(10, 10, 0, 10, 80, 0)
                sk.line(10, 80, 0, -10, 80, 0)
                sk.line(-10, 80, 0, -10, 10, 0)
            part.features.cut_midplane(100)

        def fix_slot():
            # Try with different depth
            part.features.cut_midplane(200)
            return True

        success, report = execute_with_repair(
            part,
            "Create slot",
            create_slot,
            fix_attempts=[fix_slot],
        )
        print(report.summary())
    """
    loop = AutoRepairLoop(model, max_retries=max_retries)
    return loop.execute_with_repair(
        operation_name,
        operation,
        fix_attempts=fix_attempts,
    )


RepairReportLegacy = RepairReport
