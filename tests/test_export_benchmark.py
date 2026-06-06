"""Unit tests for export and benchmark modules."""

from __future__ import annotations

from pathlib import Path

from solidworks_com.benchmark import BenchmarkCase, BenchmarkResult, BenchmarkSuite
from solidworks_com.export import ExportFormat, ExportOptions, ExportResult


class TestExportFormat:
    def test_extensions(self) -> None:
        assert ExportFormat.STEP.extension == ".step"
        assert ExportFormat.STL.extension == ".stl"
        assert ExportFormat.THREE_MF.extension == ".3mf"
        assert ExportFormat.DXF.extension == ".dxf"

    def test_descriptions(self) -> None:
        assert "STEP" in ExportFormat.STEP.description
        assert "STL" in ExportFormat.STL.description

    def test_resolve_format(self) -> None:
        # Test string resolution
        from solidworks_com.export import ExportManager

        class MockModel:
            title = "test"

        manager = ExportManager(MockModel())
        assert manager._resolve_format("step") == ExportFormat.STEP
        assert manager._resolve_format("stl") == ExportFormat.STL
        assert manager._resolve_format("3mf") == ExportFormat.THREE_MF


class TestExportOptions:
    def test_creation(self) -> None:
        opts = ExportOptions(format=ExportFormat.STEP)
        assert opts.format == ExportFormat.STEP
        assert opts.include_metadata is True

    def test_stl_options(self) -> None:
        opts = ExportOptions(
            format=ExportFormat.STL,
            stl_resolution=0.05,
            stl_ascii=True,
        )
        assert opts.stl_resolution == 0.05
        assert opts.stl_ascii is True


class TestExportResult:
    def test_success(self) -> None:
        r = ExportResult(
            success=True,
            format=ExportFormat.STEP,
            output_path=Path("test.step"),
            file_size_bytes=1024,
        )
        assert r.success is True
        assert r.file_size_bytes == 1024

    def test_failure(self) -> None:
        r = ExportResult(
            success=False,
            format=ExportFormat.STL,
            error_message="Export failed",
        )
        assert r.success is False
        assert r.error_message == "Export failed"

    def test_to_dict(self) -> None:
        r = ExportResult(success=True, format=ExportFormat.STEP)
        d = r.to_dict()
        assert d["success"] is True
        assert d["format"] == "STEP"


class TestBenchmarkCase:
    def test_creation(self) -> None:
        case = BenchmarkCase(
            name="test_case",
            description="A test benchmark",
            category="part",
        )
        assert case.name == "test_case"
        assert case.difficulty == "medium"

    def test_to_dict(self) -> None:
        case = BenchmarkCase(
            name="test",
            description="Test",
            category="part",
            expected_body_count=1,
        )
        d = case.to_dict()
        assert d["name"] == "test"
        assert d["expected_body_count"] == 1


class TestBenchmarkResult:
    def test_passed(self) -> None:
        case = BenchmarkCase(
            name="test",
            description="Test",
            category="part",
            expected_body_count=1,
        )
        r = BenchmarkResult(
            case=case,
            success=True,
            build_time_seconds=1.0,
            save_time_seconds=0.5,
            actual_body_count=1,
        )
        assert r.passed is True

    def test_failed_timing(self) -> None:
        case = BenchmarkCase(
            name="test",
            description="Test",
            category="part",
            max_build_time_seconds=1.0,
        )
        r = BenchmarkResult(
            case=case,
            success=True,
            build_time_seconds=5.0,  # Exceeds max
            actual_body_count=1,
        )
        assert r.passed is False

    def test_failed_body_count(self) -> None:
        case = BenchmarkCase(
            name="test",
            description="Test",
            category="part",
            expected_body_count=1,
        )
        r = BenchmarkResult(
            case=case,
            success=True,
            actual_body_count=2,  # Wrong count
        )
        assert r.passed is False


class TestBenchmarkSuite:
    def test_add_case(self) -> None:
        suite = BenchmarkSuite("test")
        case = BenchmarkCase(name="c1", description="Test", category="part")
        suite.add_case(case)
        assert len(suite.cases) == 1

    def test_summary(self) -> None:
        suite = BenchmarkSuite("test")
        case = BenchmarkCase(
            name="c1",
            description="Test",
            category="part",
            expected_body_count=1,
        )
        results = [
            BenchmarkResult(
                case=case,
                success=True,
                build_time_seconds=1.0,
                actual_body_count=1,
            ),
        ]
        s = suite.summary(results)
        assert "test" in s
        assert "Passed: 1" in s
