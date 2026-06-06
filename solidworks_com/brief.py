"""Natural language to CAD brief conversion.

Inspired by text-to-cad's natural-language-specs principles:
- Convert prose requirements into actionable modeling brief
- Extract dimensions, features, assumptions, validation targets
- One focused clarification question only when critical
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CABBrief:
    """Structured CAD modeling brief extracted from natural language."""

    model_name: str = "unnamed_part"
    model_type: str = "part"  # part, assembly, modification, inspection
    units: str = "mm"
    origin: str = "center"
    base_plane: str = "XY"
    up_axis: str = "+Z"

    # Dimensions
    width: float | None = None
    height: float | None = None
    depth: float | None = None
    diameter: float | None = None
    thickness: float | None = None

    # Features
    holes: list[dict[str, Any]] = field(default_factory=list)
    fillets: list[dict[str, Any]] = field(default_factory=list)
    chamfers: list[dict[str, Any]] = field(default_factory=list)
    cutouts: list[dict[str, Any]] = field(default_factory=list)
    bosses: list[dict[str, Any]] = field(default_factory=list)

    # Validation
    expected_bbox: tuple[float, float, float] | None = None
    body_count: int = 1
    validation_targets: list[str] = field(default_factory=list)

    # Metadata
    assumptions: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    clarification_needed: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Export brief as dictionary."""
        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "units": self.units,
            "origin": self.origin,
            "base_plane": self.base_plane,
            "up_axis": self.up_axis,
            "dimensions": {
                "width": self.width,
                "height": self.height,
                "depth": self.depth,
                "diameter": self.diameter,
                "thickness": self.thickness,
            },
            "features": {
                "holes": self.holes,
                "fillets": self.fillets,
                "chamfers": self.chamfers,
                "cutouts": self.cutouts,
                "bosses": self.bosses,
            },
            "validation": {
                "expected_bbox": self.expected_bbox,
                "body_count": self.body_count,
                "targets": self.validation_targets,
            },
            "assumptions": self.assumptions,
            "output_files": self.output_files,
            "clarification_needed": self.clarification_needed,
        }

    def summary(self) -> str:
        """Generate human-readable brief summary."""
        lines = [f"CAD Brief: {self.model_name}"]
        lines.append(f"  Type: {self.model_type}")
        lines.append(f"  Units: {self.units}")
        lines.append(f"  Origin: {self.origin}, Base: {self.base_plane}, Up: {self.up_axis}")

        if self.width or self.height or self.depth:
            dims = []
            if self.width:
                dims.append(f"W={self.width}")
            if self.height:
                dims.append(f"H={self.height}")
            if self.depth:
                dims.append(f"D={self.depth}")
            lines.append(f"  Dimensions: {', '.join(dims)} {self.units}")

        if self.diameter:
            lines.append(f"  Diameter: {self.diameter} {self.units}")

        if self.holes:
            lines.append(f"  Holes: {len(self.holes)}")
        if self.fillets:
            lines.append(f"  Fillets: {len(self.fillets)}")
        if self.cutouts:
            lines.append(f"  Cutouts: {len(self.cutouts)}")

        if self.assumptions:
            lines.append(f"  Assumptions: {len(self.assumptions)}")
            for a in self.assumptions[:3]:
                lines.append(f"    - {a}")

        return "\n".join(lines)


class BriefParser:
    """Parse natural language into CABBrief."""

    # Common dimension patterns
    DIM_PATTERNS = [
        # "100 mm by 60 mm by 6 mm"
        r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)',
        # "100 x 60 x 6"
        r'(\d+(?:\.\d+)?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)',
        # "100mm x 60mm x 6mm"
        r'(\d+(?:\.\d+)?)\s*mm\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*mm\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*mm',
    ]

    # Feature patterns
    HOLE_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*(?:diameter\s*)?(?:through[- ]?)?holes?',
        re.IGNORECASE
    )

    def parse(self, text: str) -> CABBrief:
        """Parse natural language text into a CABBrief."""
        brief = CABBrief()
        text_lower = text.lower()

        # Extract model name
        brief.model_name = self._extract_model_name(text)

        # Extract dimensions
        self._extract_dimensions(text, brief)

        # Extract features
        self._extract_features(text, brief)

        # Extract units
        if "inch" in text_lower or '"' in text:
            brief.units = "inch"
        elif "cm" in text_lower or "centimeter" in text_lower:
            brief.units = "cm"

        # Generate assumptions
        self._generate_assumptions(brief)

        # Set validation targets
        brief.validation_targets = [
            "bounding_box",
            "body_count",
            "feature_errors",
        ]

        # Check if clarification needed
        if not brief.width and not brief.height and not brief.depth and not brief.diameter:
            brief.clarification_needed = "No dimensions specified. Please provide dimensions."

        return brief

    def _extract_model_name(self, text: str) -> str:
        """Extract a reasonable model name from text."""
        text_lower = text.lower()

        # Common part types
        part_types = [
            "plate", "bracket", "enclosure", "shaft", "gear", "pulley",
            "flange", "housing", "mount", "adapter", "spacer", "bushing",
            "washer", "nut", "bolt", "screw", "standoff", "boss",
        ]

        for ptype in part_types:
            if ptype in text_lower:
                # Look for adjective before part type
                pattern = rf'(\w+)\s+{ptype}'
                match = re.search(pattern, text_lower)
                if match:
                    return f"{match.group(1)}_{ptype}"
                return ptype

        return "unnamed_part"

    def _extract_dimensions(self, text: str, brief: CABBrief) -> None:
        """Extract dimensions from text."""
        for pattern in self.DIM_PATTERNS:
            match = re.search(pattern, text)
            if match:
                brief.width = float(match.group(1))
                brief.height = float(match.group(2))
                brief.depth = float(match.group(3))
                brief.expected_bbox = (brief.width, brief.height, brief.depth)
                return

        # Try to find single diameter
        diam_match = re.search(r'(?:diameter|dia\.?|Ø)\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)?', text, re.IGNORECASE)
        if diam_match:
            brief.diameter = float(diam_match.group(1))

        # Try to find thickness
        thick_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*(?:thick|thickness)', text, re.IGNORECASE)
        if thick_match:
            brief.thickness = float(thick_match.group(1))
        # Also try "thickness Xmm" pattern
        thick_match2 = re.search(r'thickness\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)?', text, re.IGNORECASE)
        if thick_match2 and not brief.thickness:
            brief.thickness = float(thick_match2.group(1))

    def _extract_features(self, text: str, brief: CABBrief) -> None:
        """Extract features from text."""
        text_lower = text.lower()

        # Pattern: "four 4.5mm holes" or "four through holes" or "4 holes"
        hole_match = re.search(
            r'(four|five|six|seven|eight|nine|ten|\d+)\s+(?:(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*)?(?:through[- ]?)?holes?',
            text_lower
        )
        if hole_match:
            # Get count
            count_str = hole_match.group(1)
            word_to_num = {"four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            count = int(count_str) if count_str.isdigit() else word_to_num.get(count_str, 4)

            # Get diameter if specified
            diameter = 4.5  # Default M4 clearance
            if hole_match.group(2):
                diameter = float(hole_match.group(2))

            for _ in range(count):
                brief.holes.append({"diameter": diameter, "type": "through"})

        # Extract fillets
        fillet_match = re.search(r'(?:rounded?\s*corners?|fillets?|R\s*(\d+(?:\.\d+)?))', text, re.IGNORECASE)
        if fillet_match:
            radius = 3.0  # Default cosmetic fillet
            if fillet_match.group(1):
                with contextlib.suppress(ValueError, IndexError):
                    radius = float(fillet_match.group(1))
            brief.fillets.append({"radius": radius})

        # Extract chamfers
        chamfer_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*chamfers?', text, re.IGNORECASE)
        if chamfer_match:
            size = float(chamfer_match.group(1))
            brief.chamfers.append({"size": size})

        # Extract cutouts
        cutout_match = re.search(r'(\d+)\s*(?:by|x|×)\s*(\d+)\s*(?:mm|millimeters?)?\s*(?:rectangular?\s*)?cutout', text_lower)
        if cutout_match:
            brief.cutouts.append({
                "width": float(cutout_match.group(1)),
                "height": float(cutout_match.group(2)),
                "type": "rectangular",
            })

    def _generate_assumptions(self, brief: CABBrief) -> None:
        """Generate reasonable assumptions for missing information."""
        if brief.width and brief.height and not brief.depth:
            brief.assumptions.append("Thickness not specified; assuming 6mm")
            brief.depth = 6.0

        if brief.holes and not any(h.get("diameter") for h in brief.holes):
            brief.assumptions.append("Hole diameter not specified; assuming M4 clearance (4.5mm)")

        if not brief.fillets and brief.width and brief.width > 20:
            brief.assumptions.append("No fillets specified; adding 1mm cosmetic fillets on outer edges")
            brief.fillets.append({"radius": 1.0})

        if brief.diameter and not brief.depth:
            brief.assumptions.append("Cylinder length not specified; assuming equal to diameter")
            brief.depth = brief.diameter


def parse_brief(text: str) -> CABBrief:
    """Convenience function to parse natural language into CABBrief.

    Example::

        brief = parse_brief("Make a 100mm by 60mm by 6mm mounting plate with four 4.5mm holes")
        print(brief.summary())
    """
    parser = BriefParser()
    return parser.parse(text)
