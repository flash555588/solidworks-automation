"""Unit tests for analysis and metadata modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from solidworks_com.analysis import GeometryFacts, ValidationReport, ValidationResult
from solidworks_com.metadata import GenerationMetadata, MetadataManager


class TestGeometryFacts:
    def test_creation(self) -> None:
        facts = GeometryFacts()
        assert facts.bbox_min is None
        assert facts.body_count == 0

    def test_to_dict(self) -> None:
        facts = GeometryFacts(
            bbox_min=(0.0, 0.0, 0.0),
            bbox_max=(1.0, 2.0, 3.0),
            size=(1.0, 2.0, 3.0),
            center=(0.5, 1.0, 1.5),
            diagonal=3.7416573867739413,
            extent_axis='z',
            body_count=1,
        )
        d = facts.to_dict()
        assert d["bbox"]["min"] == [0.0, 0.0, 0.0]
        assert d["size"] == [1.0, 2.0, 3.0]
        assert d["extentAxis"] == 'z'


class TestValidationResult:
    def test_passed(self) -> None:
        r = ValidationResult(check_name="size_x", passed=True, expected=1.0, actual=1.0)
        assert r.passed is True

    def test_failed(self) -> None:
        r = ValidationResult(
            check_name="size_x",
            passed=False,
            expected=1.0,
            actual=0.5,
            tolerance=0.001,
            message="Size mismatch",
        )
        assert r.passed is False
        assert r.message == "Size mismatch"

    def test_to_dict(self) -> None:
        r = ValidationResult(check_name="test", passed=True)
        d = r.to_dict()
        assert d["check"] == "test"
        assert d["passed"] is True


class TestValidationReport:
    def test_empty_report(self) -> None:
        r = ValidationReport()
        assert r.success is True
        assert r.total_checks == 0

    def test_add_results(self) -> None:
        r = ValidationReport()
        r.add_result(ValidationResult(check_name="test1", passed=True))
        r.add_result(ValidationResult(check_name="test2", passed=False, message="failed"))
        assert r.total_checks == 2
        assert r.passed_checks == 1
        assert r.failed_checks == 1
        assert r.success is False

    def test_summary(self) -> None:
        r = ValidationReport(model_name="test_model")
        r.add_result(ValidationResult(check_name="size", passed=True))
        s = r.summary()
        assert "test_model" in s
        assert "1/1 passed" in s

    def test_to_dict(self) -> None:
        r = ValidationReport(model_name="test")
        d = r.to_dict()
        assert d["model"] == "test"
        assert d["summary"]["success"] is True


class TestGenerationMetadata:
    def test_creation(self) -> None:
        m = GenerationMetadata()
        assert m.source_file is None
        assert m.validation_passed is None

    def test_to_dict(self) -> None:
        m = GenerationMetadata(
            source_file="test.py",
            source_hash="abc123",
            generated_at="2026-01-01T00:00:00Z",
            output_file="test.SLDPRT",
            validation_passed=True,
        )
        d = m.to_dict()
        assert d["source"]["file"] == "test.py"
        assert d["generation"]["timestamp"] == "2026-01-01T00:00:00Z"
        assert d["validation"]["passed"] is True

    def test_to_json(self) -> None:
        m = GenerationMetadata(source_file="test.py")
        j = m.to_json()
        parsed = json.loads(j)
        assert parsed["source"]["file"] == "test.py"


class TestMetadataManager:
    def test_record_source(self) -> None:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('hello')\n")
            temp_path = f.name

        try:
            manager = MetadataManager(None)
            manager.record_source(temp_path)
            assert manager.metadata.source_file == temp_path
            assert manager.metadata.source_hash is not None
            assert manager.metadata.source_lines == 1
        finally:
            Path(temp_path).unlink()

    def test_record_generation(self) -> None:
        manager = MetadataManager(None)
        manager.record_generation(generator_name="test", version="1.0.0")
        assert manager.metadata.generator_name == "test"
        assert manager.metadata.generated_at is not None

    def test_record_validation(self) -> None:
        manager = MetadataManager(None)
        manager.record_validation(passed=True, checks=5, failures=0)
        assert manager.metadata.validation_passed is True
        assert manager.metadata.validation_checks == 5

    def test_properties(self) -> None:
        manager = MetadataManager(None)
        manager.set_property("key1", "value1")
        assert manager.get_property("key1") == "value1"
        assert manager.get_property("missing", "default") == "default"

    def test_save_load(self) -> None:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            # Create and save metadata with direct property setting
            manager = MetadataManager(None)
            manager.metadata.source_file = "test.py"
            manager.metadata.source_hash = "abc123"
            manager.metadata.source_lines = 10
            manager.metadata.generated_at = "2026-01-01T00:00:00Z"
            manager.metadata.generator_name = "test"
            manager.save(temp_path)

            # Load and verify
            manager2 = MetadataManager(None)
            manager2.load(temp_path)
            assert manager2.metadata.source_file == "test.py"
            assert manager2.metadata.source_hash == "abc123"
            assert manager2.metadata.generator_name == "test"
        finally:
            Path(temp_path).unlink()
