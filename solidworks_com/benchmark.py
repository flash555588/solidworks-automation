"""Benchmark suite for solidworks-com.

Inspired by text-to-cad's benchmark system:
- Standardized test cases
- Reproducible results
- Performance tracking
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkCase:
    """A single benchmark test case."""

    name: str
    description: str
    category: str  # "part", "assembly", "feature"

    # Build function
    build_fn: Callable[..., Any] | None = None

    # Expected results
    expected_features: int | None = None
    expected_body_count: int = 1
    expected_dimensions: tuple[float, float, float] | None = None

    # Performance thresholds
    max_build_time_seconds: float = 30.0
    max_save_time_seconds: float = 10.0

    # Metadata
    difficulty: str = "medium"  # "easy", "medium", "hard"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "expected_features": self.expected_features,
            "expected_body_count": self.expected_body_count,
            "expected_dimensions": self.expected_dimensions,
            "max_build_time_seconds": self.max_build_time_seconds,
            "max_save_time_seconds": self.max_save_time_seconds,
            "difficulty": self.difficulty,
            "tags": self.tags,
        }


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    case: BenchmarkCase
    success: bool

    # Timing
    build_time_seconds: float = 0.0
    save_time_seconds: float = 0.0
    total_time_seconds: float = 0.0

    # Actual results
    actual_features: int | None = None
    actual_body_count: int | None = None
    actual_dimensions: tuple[float, float, float] | None = None

    # Errors
    error_message: str | None = None
    validation_errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "success": self.success,
            "timing": {
                "build_seconds": self.build_time_seconds,
                "save_seconds": self.save_time_seconds,
                "total_seconds": self.total_time_seconds,
            },
            "actual": {
                "features": self.actual_features,
                "body_count": self.actual_body_count,
                "dimensions": self.actual_dimensions,
            },
            "error_message": self.error_message,
            "validation_errors": self.validation_errors,
        }

    @property
    def passed(self) -> bool:
        """Check if the benchmark passed all validations."""
        if not self.success:
            return False

        # Check timing
        if self.build_time_seconds > self.case.max_build_time_seconds:
            return False
        if self.save_time_seconds > self.case.max_save_time_seconds:
            return False

        # Check body count
        return self.actual_body_count == self.case.expected_body_count


class BenchmarkSuite:
    """A suite of benchmark test cases."""

    def __init__(self, name: str = "solidworks-com benchmarks") -> None:
        self.name = name
        self.cases: list[BenchmarkCase] = []

    def add_case(self, case: BenchmarkCase) -> None:
        """Add a benchmark case to the suite."""
        self.cases.append(case)

    def run(
        self,
        *,
        output_dir: Path | None = None,
        run_filter: Callable[[BenchmarkCase], bool] | None = None,
    ) -> list[BenchmarkResult]:
        """Run all benchmark cases.

        Args:
            output_dir: Directory for output files.
            run_filter: Optional filter function for cases.

        Returns:
            List of BenchmarkResult for each case.
        """
        results = []

        for case in self.cases:
            if run_filter and not run_filter(case):
                continue

            logger.info(f"Running benchmark: {case.name}")
            result = self._run_case(case, output_dir)
            results.append(result)

        return results

    def _run_case(self, case: BenchmarkCase, output_dir: Path | None) -> BenchmarkResult:
        """Run a single benchmark case."""
        if case.build_fn is None:
            return BenchmarkResult(
                case=case,
                success=False,
                error_message="No build function defined",
            )

        start_time = time.time()

        try:
            # Build the model
            build_start = time.time()
            model = case.build_fn()
            build_time = time.time() - build_start

            # Save the model
            save_start = time.time()
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{case.name}.SLDPRT"
                model.save_as(output_path)
            save_time = time.time() - save_start

            total_time = time.time() - start_time

            # Get actual results
            actual_features = None
            actual_body_count = None
            actual_dimensions = None

            try:
                # Try to get feature count
                features = list(model.iter_features())
                actual_features = len(features)
            except Exception:
                pass

            try:
                # Try to get body count
                bodies = model.bodies()
                actual_body_count = len(bodies) if bodies else 0
            except Exception:
                pass

            try:
                # Try to get dimensions
                box = model.com.Extension.GetBox()
                if box and len(box) >= 6:
                    actual_dimensions = (
                        float(box[3]) - float(box[0]),
                        float(box[4]) - float(box[1]),
                        float(box[5]) - float(box[2]),
                    )
            except Exception:
                pass

            # Validate
            validation_errors = []
            if case.expected_body_count is not None and actual_body_count != case.expected_body_count:
                validation_errors.append(
                    f"Body count: expected {case.expected_body_count}, got {actual_body_count}"
                )

            return BenchmarkResult(
                case=case,
                success=True,
                build_time_seconds=build_time,
                save_time_seconds=save_time,
                total_time_seconds=total_time,
                actual_features=actual_features,
                actual_body_count=actual_body_count,
                actual_dimensions=actual_dimensions,
                validation_errors=validation_errors if validation_errors else None,
            )

        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"Benchmark '{case.name}' failed: {e}")
            return BenchmarkResult(
                case=case,
                success=False,
                total_time_seconds=total_time,
                error_message=str(e),
            )

    def summary(self, results: list[BenchmarkResult]) -> str:
        """Generate a summary of benchmark results."""
        lines = [f"Benchmark Suite: {self.name}"]
        lines.append(f"  Total cases: {len(results)}")

        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        lines.append(f"  Passed: {len(passed)}")
        lines.append(f"  Failed: {len(failed)}")

        if failed:
            lines.append("\nFailed cases:")
            for r in failed:
                lines.append(f"  - {r.case.name}: {r.error_message or 'Validation failed'}")

        # Timing summary
        if results:
            total_build = sum(r.build_time_seconds for r in results)
            total_save = sum(r.save_time_seconds for r in results)
            lines.append("\nTiming:")
            lines.append(f"  Total build time: {total_build:.2f}s")
            lines.append(f"  Total save time: {total_save:.2f}s")

        return "\n".join(lines)


# Standard benchmark cases
def create_standard_benchmarks() -> BenchmarkSuite:
    """Create a standard benchmark suite."""
    suite = BenchmarkSuite("solidworks-com standard benchmarks")

    # These would be populated with actual benchmark functions
    # For now, they're placeholders

    return suite
