"""Metadata management for model generation.

Inspired by text-to-cad's metadata tracking:
- Source code hashing
- Generation timestamps
- Version tracking
- Validation history
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GenerationMetadata:
    """Metadata for a model generation."""

    # Source information
    source_file: str | None = None
    source_hash: str | None = None
    source_lines: int | None = None

    # Generation info
    generated_at: str | None = None
    generator_version: str | None = None
    generator_name: str | None = None

    # Output information
    output_file: str | None = None
    output_format: str = "SLDPRT"
    output_size_bytes: int | None = None

    # Validation
    validation_passed: bool | None = None
    validation_checks: int = 0
    validation_failures: int = 0

    # Custom properties
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "file": self.source_file,
                "hash": self.source_hash,
                "lines": self.source_lines,
            },
            "generation": {
                "timestamp": self.generated_at,
                "version": self.generator_version,
                "generator": self.generator_name,
            },
            "output": {
                "file": self.output_file,
                "format": self.output_format,
                "sizeBytes": self.output_size_bytes,
            },
            "validation": {
                "passed": self.validation_passed,
                "checks": self.validation_checks,
                "failures": self.validation_failures,
            },
            "properties": self.properties,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class MetadataManager:
    """Manages model generation metadata."""

    def __init__(self, model: Any) -> None:
        self.model = model
        self._metadata: GenerationMetadata | None = None

    @property
    def metadata(self) -> GenerationMetadata:
        if self._metadata is None:
            self._metadata = GenerationMetadata()
        return self._metadata

    def record_source(self, source_path: str | Path | None = None) -> None:
        """Record source file information."""
        if source_path is None:
            return

        source_path = Path(source_path)
        if not source_path.exists():
            logger.warning("Source file not found: %s", source_path)
            return

        self.metadata.source_file = str(source_path)
        self.metadata.source_hash = self._compute_file_hash(source_path)
        self.metadata.source_lines = self._count_lines(source_path)

    def record_generation(self, *, generator_name: str | None = None, version: str | None = None) -> None:
        """Record generation information."""
        self.metadata.generated_at = datetime.now(timezone.utc).isoformat()
        self.metadata.generator_name = generator_name
        self.metadata.generator_version = version

    def record_output(self, output_path: str | Path | None = None, format: str = "SLDPRT") -> None:
        """Record output file information."""
        if output_path is None:
            return

        output_path = Path(output_path)
        self.metadata.output_file = str(output_path)
        self.metadata.output_format = format

        if output_path.exists():
            self.metadata.output_size_bytes = output_path.stat().st_size

    def record_validation(self, passed: bool, checks: int, failures: int) -> None:
        """Record validation results."""
        self.metadata.validation_passed = passed
        self.metadata.validation_checks = checks
        self.metadata.validation_failures = failures

    def set_property(self, key: str, value: Any) -> None:
        """Set a custom property."""
        self.metadata.properties[key] = value

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a custom property."""
        return self.metadata.properties.get(key, default)

    def save(self, output_path: str | Path) -> None:
        """Save metadata to a JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.metadata.to_json())

        logger.info("Saved metadata to %s", output_path)

    def load(self, input_path: str | Path) -> None:
        """Load metadata from a JSON file."""
        input_path = Path(input_path)
        if not input_path.exists():
            logger.warning("Metadata file not found: %s", input_path)
            return

        with open(input_path, encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid metadata format in {input_path}: expected a JSON object")
        for section in ("source", "generation"):
            if section in data and not isinstance(data[section], dict):
                raise ValueError(f"Invalid metadata section '{section}' in {input_path}: expected an object")

        # Map dict back to dataclass
        m = self.metadata
        if "source" in data:
            m.source_file = data["source"].get("file")
            m.source_hash = data["source"].get("hash")
            m.source_lines = data["source"].get("lines")
        if "generation" in data:
            m.generated_at = data["generation"].get("timestamp")
            m.generator_version = data["generation"].get("version")
            m.generator_name = data["generation"].get("generator")
        if "output" in data:
            m.output_file = data["output"].get("file")
            m.output_format = data["output"].get("format", "SLDPRT")
            m.output_size_bytes = data["output"].get("sizeBytes")
        if "validation" in data:
            m.validation_passed = data["validation"].get("passed")
            m.validation_checks = data["validation"].get("checks", 0)
            m.validation_failures = data["validation"].get("failures", 0)
        if "properties" in data:
            m.properties = data["properties"]

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except (OSError, ValueError) as e:
            logger.debug("Failed to compute hash: %s", e)
            return ""

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a text file."""
        try:
            with open(file_path, encoding='utf-8') as f:
                return sum(1 for _ in f)
        except (OSError, ValueError) as e:
            logger.debug("Failed to count lines: %s", e)
            return 0


def create_metadata_manager(model: Any) -> MetadataManager:
    """Create a MetadataManager for the given model.

    Example::

        manager = create_metadata_manager(part)
        manager.record_source("examples/model_bracket.py")
        manager.record_generation(generator_name="solidworks-com", version="1.0.0")
        manager.record_output("output/bracket.SLDPRT")
        manager.record_validation(passed=True, checks=5, failures=0)
        manager.save("output/bracket.metadata.json")
    """
    return MetadataManager(model)
