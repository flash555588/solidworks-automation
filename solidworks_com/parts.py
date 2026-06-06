"""Standard parts library for common CAD components.

Inspired by cadskills.xyz's step.parts skill:
- Find off-the-shelf STEP parts
- Screws, bearings, motors, connectors
- Local caching for fast access
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PartCategory(Enum):
    """Categories of standard parts."""

    SCREW = auto()
    BOLT = auto()
    NUT = auto()
    WASHER = auto()
    BEARING = auto()
    GEAR = auto()
    MOTOR = auto()
    CONNECTOR = auto()
    BRACKET = auto()
    SHAFT = auto()


class PartStandard(Enum):
    """Standards for parts."""

    ISO = auto()       # International
    DIN = auto()       # German
    ANSI = auto()      # American
    JIS = auto()       # Japanese
    GB = auto()        # Chinese


@dataclass
class StandardPart:
    """A standard part definition."""

    name: str
    category: PartCategory
    standard: PartStandard
    size: str              # e.g., "M6", "1/4-20"
    description: str
    file_path: Path | None = None
    dimensions: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.name,
            "standard": self.standard.name,
            "size": self.size,
            "description": self.description,
            "filePath": str(self.file_path) if self.file_path else None,
            "dimensions": self.dimensions,
        }


# Common metric screws (ISO 4762 - Socket Head Cap Screw)
METRIC_SCREWS = {
    "M3": {"diameter": 0.003, "head_dia": 0.0055, "head_height": 0.003},
    "M4": {"diameter": 0.004, "head_dia": 0.007, "head_height": 0.004},
    "M5": {"diameter": 0.005, "head_dia": 0.0085, "head_height": 0.005},
    "M6": {"diameter": 0.006, "head_dia": 0.010, "head_height": 0.006},
    "M8": {"diameter": 0.008, "head_dia": 0.013, "head_height": 0.008},
    "M10": {"diameter": 0.010, "head_dia": 0.016, "head_height": 0.010},
    "M12": {"diameter": 0.012, "head_dia": 0.018, "head_height": 0.012},
}


class PartsLibrary:
    """Library of standard parts."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or Path.home() / ".solidworks_com" / "parts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._parts: dict[str, StandardPart] = {}
        self._load_builtin_parts()

    def _load_builtin_parts(self) -> None:
        """Load built-in part definitions."""
        # Add metric screws
        for size, dims in METRIC_SCREWS.items():
            self._parts[f"screw_{size}"] = StandardPart(
                name=f"Socket Head Cap Screw {size}",
                category=PartCategory.SCREW,
                standard=PartStandard.ISO,
                size=size,
                description=f"ISO 4762 {size} socket head cap screw",
                dimensions=dims,
            )

    def search(
        self,
        query: str,
        *,
        category: PartCategory | None = None,
        standard: PartStandard | None = None,
    ) -> list[StandardPart]:
        """Search for parts.

        Args:
            query: Search query (size, name, etc.).
            category: Filter by category.
            standard: Filter by standard.

        Returns:
            List of matching parts.
        """
        results = []
        query_lower = query.lower()

        for part in self._parts.values():
            # Apply filters
            if category and part.category != category:
                continue
            if standard and part.standard != standard:
                continue

            # Search in name, size, description
            if (
                query_lower in part.name.lower()
                or query_lower in part.size.lower()
                or query_lower in part.description.lower()
            ):
                results.append(part)

        return results

    def get_part(self, name: str) -> StandardPart | None:
        """Get a part by name."""
        return self._parts.get(name)

    def list_parts(
        self,
        *,
        category: PartCategory | None = None,
    ) -> list[StandardPart]:
        """List all parts.

        Args:
            category: Filter by category.

        Returns:
            List of parts.
        """
        if category:
            return [p for p in self._parts.values() if p.category == category]
        return list(self._parts.values())

    def add_part(self, part: StandardPart) -> None:
        """Add a custom part to the library."""
        key = f"{part.category.name.lower()}_{part.size}"
        self._parts[key] = part

    def get_screw(self, size: str, length: float) -> StandardPart | None:
        """Get a screw by size and length.

        Args:
            size: Screw size (e.g., "M6").
            length: Screw length in meters.

        Returns:
            StandardPart or None if not found.
        """
        key = f"screw_{size}"
        part = self._parts.get(key)
        if part:
            # Create a copy with specified length
            return StandardPart(
                name=f"{part.name} x {length*1000:.0f}mm",
                category=part.category,
                standard=part.standard,
                size=part.size,
                description=f"{part.description} x {length*1000:.0f}mm",
                dimensions={
                    **(part.dimensions or {}),
                    "length": length,
                },
            )
        return None


def create_parts_library(cache_dir: Path | None = None) -> PartsLibrary:
    """Create a parts library.

    Example::

        from solidworks_com import create_parts_library

        # Create library
        library = create_parts_library()

        # Search for screws
        screws = library.search("M6", category=PartCategory.SCREW)

        # Get specific screw
        screw = library.get_screw("M6", 0.020)  # M6 x 20mm
    """
    return PartsLibrary(cache_dir)
