"""Engineering drawing parser.

Parses engineering drawings from images to extract:
- Dimensions and measurements
- Geometric features (holes, slots, fillets)
- Views (front, side, top)
- Tolerances and annotations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Dimension:
    """A dimension extracted from drawing."""

    value: float
    unit: str = "mm"
    label: str = ""
    view: str = ""  # "front", "side", "top"
    axis: str = ""  # "x", "y", "z"

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "label": self.label,
            "view": self.view,
            "axis": self.axis,
        }


@dataclass
class Feature:
    """A geometric feature extracted from drawing."""

    type: str  # "hole", "slot", "fillet", "chamfer", "pocket", "boss"
    size: float | None = None
    diameter: float | None = None
    depth: float | None = None
    radius: float | None = None
    position: tuple[float, float] | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "size": self.size,
            "diameter": self.diameter,
            "depth": self.depth,
            "radius": self.radius,
            "position": self.position,
            "label": self.label,
        }


@dataclass
class DrawingView:
    """A view extracted from drawing."""

    name: str  # "front", "side", "top", "isometric"
    width: float | None = None
    height: float | None = None
    features: list[Feature] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "features": [f.to_dict() for f in self.features],
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


@dataclass
class ParsedDrawing:
    """Complete parsed drawing."""

    title: str = ""
    views: list[DrawingView] = field(default_factory=list)
    overall_dimensions: list[Dimension] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> float | None:
        """Get overall width."""
        for dim in self.overall_dimensions:
            if dim.axis == "x":
                return dim.value
        return None

    @property
    def height(self) -> float | None:
        """Get overall height."""
        for dim in self.overall_dimensions:
            if dim.axis == "y":
                return dim.value
        return None

    @property
    def depth(self) -> float | None:
        """Get overall depth."""
        for dim in self.overall_dimensions:
            if dim.axis == "z":
                return dim.value
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "views": [v.to_dict() for v in self.views],
            "overallDimensions": [d.to_dict() for d in self.overall_dimensions],
            "features": [f.to_dict() for f in self.features],
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        lines = [f"Parsed Drawing: {self.title}"]

        if self.width or self.height or self.depth:
            dims = []
            if self.width:
                dims.append(f"W={self.width:.1f}mm")
            if self.height:
                dims.append(f"H={self.height:.1f}mm")
            if self.depth:
                dims.append(f"D={self.depth:.1f}mm")
            lines.append(f"  Overall: {', '.join(dims)}")

        lines.append(f"  Views: {len(self.views)}")
        lines.append(f"  Features: {len(self.features)}")

        if self.features:
            for f in self.features[:5]:
                lines.append(f"    - {f.type}: {f.diameter or f.size or 'N/A'}")

        return "\n".join(lines)


class DrawingParser:
    """Parses engineering drawings from images."""

    def parse_image(self, image_path: str | Path) -> ParsedDrawing:
        """Parse an engineering drawing image.

        .. warning::
            This method is not fully implemented. Image-based drawing
            parsing requires a vision API and is not yet available.
            Use :meth:`parse_text_description` for now.

        Args:
            image_path: Path to the image file.

        Returns:
            ParsedDrawing with basic metadata only.
        """
        import warnings
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        warnings.warn(
            "DrawingParser.parse_image is not fully implemented. "
            "Only basic metadata is returned. Use parse_text_description instead.",
            UserWarning,
            stacklevel=2,
        )
        return ParsedDrawing(
            title=image_path.stem,
            metadata={"source": str(image_path)},
        )

    def parse_text_description(self, description: str) -> ParsedDrawing:
        """Parse drawing from text description.

        Args:
            description: Text description of the drawing.

        Returns:
            ParsedDrawing with extracted information.
        """
        drawing = ParsedDrawing(title="From description")

        # Extract dimensions from text
        import re

        # Pattern: "100 x 60 x 6" or "100mm x 60mm x 6mm"
        dim_pattern = r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)?\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)?\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)?'
        match = re.search(dim_pattern, description, re.IGNORECASE)
        if match:
            drawing.overall_dimensions = [
                Dimension(value=float(match.group(1)), unit="mm", axis="x", label="width"),
                Dimension(value=float(match.group(2)), unit="mm", axis="y", label="height"),
                Dimension(value=float(match.group(3)), unit="mm", axis="z", label="depth"),
            ]

        # Extract holes
        hole_pattern = r'(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\s*(?:diameter\s*)?(?:through[- ]?)?holes?'
        hole_matches = re.findall(hole_pattern, description, re.IGNORECASE)
        for match in hole_matches:
            drawing.features.append(Feature(
                type="hole",
                diameter=float(match),
            ))

        # Extract fillets
        fillet_pattern = r'(?:rounded?\s*corners?|fillets?|R\s*(\d+(?:\.\d+)?))'
        fillet_match = re.search(fillet_pattern, description, re.IGNORECASE)
        if fillet_match:
            radius = float(fillet_match.group(1)) if fillet_match.group(1) else 3.0
            drawing.features.append(Feature(
                type="fillet",
                radius=radius,
            ))

        return drawing


def parse_drawing(
    image_path: str | Path | None = None,
    description: str | None = None,
) -> ParsedDrawing:
    """Convenience function to parse a drawing.

    Args:
        image_path: Path to engineering drawing image.
        description: Text description of the drawing.

    Returns:
        ParsedDrawing with extracted information.

    Example::

        from solidworks_com import parse_drawing

        # Parse from image
        drawing = parse_drawing("bracket_drawing.png")

        # Parse from text
        drawing = parse_drawing(
            description="Make a 100mm by 60mm by 6mm plate with four 4.5mm holes"
        )

        print(drawing.summary())
    """
    parser = DrawingParser()

    if image_path:
        return parser.parse_image(image_path)
    elif description:
        return parser.parse_text_description(description)
    else:
        raise ValueError("Either image_path or description must be provided")
