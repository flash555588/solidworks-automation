"""Unit tests for solidworks_com.metadata (no SOLIDWORKS required)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from solidworks_com.metadata import GenerationMetadata, MetadataManager, create_metadata_manager


class TestGenerationMetadata:
    def test_defaults(self) -> None:
        m = GenerationMetadata()
        assert m.output_format == "SLDPRT"
        assert m.validation_checks == 0
        assert m.properties == {}

    def test_to_dict_structure(self) -> None:
        m = GenerationMetadata(
            source_file="foo.py",
            output_file="bar.SLDPRT",
            validation_passed=True,
        )
        d = m.to_dict()
        for section in ("source", "generation", "output", "validation", "properties"):
            assert section in d

    def test_to_dict_source_file(self) -> None:
        m = GenerationMetadata(source_file="foo.py")
        assert m.to_dict()["source"]["file"] == "foo.py"

    def test_to_json_is_valid(self) -> None:
        m = GenerationMetadata(generator_name="test")
        parsed = json.loads(m.to_json())
        assert parsed["generation"]["generator"] == "test"

    def test_to_json_indent(self) -> None:
        m = GenerationMetadata()
        j = m.to_json(indent=4)
        assert "    " in j


class TestMetadataManager:
    def _make_manager(self) -> MetadataManager:
        model = MagicMock()
        return MetadataManager(model)

    def test_metadata_lazy_init(self) -> None:
        mgr = self._make_manager()
        assert mgr._metadata is None
        _ = mgr.metadata
        assert mgr._metadata is not None

    def test_record_generation(self) -> None:
        mgr = self._make_manager()
        mgr.record_generation(generator_name="sw-com", version="1.0")
        assert mgr.metadata.generator_name == "sw-com"
        assert mgr.metadata.generator_version == "1.0"
        assert mgr.metadata.generated_at is not None

    def test_record_source_missing_file(self) -> None:
        mgr = self._make_manager()
        mgr.record_source("/nonexistent/path.py")
        assert mgr.metadata.source_file is None

    def test_record_source_existing_file(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("x = 1\ny = 2\n")
        mgr = self._make_manager()
        mgr.record_source(src)
        assert mgr.metadata.source_file == str(src)
        assert mgr.metadata.source_lines == 2
        assert len(mgr.metadata.source_hash) == 64  # SHA256 hex

    def test_record_output_existing_file(self, tmp_path: Path) -> None:
        out = tmp_path / "part.SLDPRT"
        out.write_bytes(b"placeholder")
        mgr = self._make_manager()
        mgr.record_output(out, format="SLDPRT")
        assert mgr.metadata.output_file == str(out)
        assert mgr.metadata.output_size_bytes == len(b"placeholder")

    def test_record_output_none(self) -> None:
        mgr = self._make_manager()
        mgr.record_output(None)
        assert mgr.metadata.output_file is None

    def test_record_validation(self) -> None:
        mgr = self._make_manager()
        mgr.record_validation(passed=True, checks=5, failures=0)
        assert mgr.metadata.validation_passed is True
        assert mgr.metadata.validation_checks == 5

    def test_set_and_get_property(self) -> None:
        mgr = self._make_manager()
        mgr.set_property("foo", 42)
        assert mgr.get_property("foo") == 42

    def test_get_missing_property_returns_default(self) -> None:
        mgr = self._make_manager()
        assert mgr.get_property("missing", "default") == "default"

    def test_save_creates_json_file(self, tmp_path: Path) -> None:
        mgr = self._make_manager()
        mgr.record_generation(generator_name="test")
        out = tmp_path / "meta.json"
        mgr.save(out)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["generation"]["generator"] == "test"

    def test_load_round_trip(self, tmp_path: Path) -> None:
        mgr = self._make_manager()
        mgr.record_generation(generator_name="round-trip-test", version="2.0")
        mgr.record_validation(passed=True, checks=3, failures=0)
        out = tmp_path / "meta.json"
        mgr.save(out)

        mgr2 = self._make_manager()
        mgr2.load(out)
        assert mgr2.metadata.generator_name == "round-trip-test"
        assert mgr2.metadata.generator_version == "2.0"
        assert mgr2.metadata.validation_checks == 3

    def test_load_missing_file(self) -> None:
        mgr = self._make_manager()
        mgr.load("/nonexistent/meta.json")
        assert mgr._metadata is None or mgr.metadata.generator_name is None

    def test_load_invalid_format_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")
        mgr = self._make_manager()
        with pytest.raises(ValueError):
            mgr.load(bad)


class TestCreateMetadataManager:
    def test_returns_manager(self) -> None:
        model = MagicMock()
        mgr = create_metadata_manager(model)
        assert isinstance(mgr, MetadataManager)
        assert mgr.model is model
