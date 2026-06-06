"""Engineering drawing generator.

Generates 2D engineering drawings from 3D models for:
- Manufacturing documentation
- Assembly instructions
- Quality inspection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ViewType(Enum):
    """Types of engineering views."""

    FRONT = auto()
    TOP = auto()
    RIGHT = auto()
    LEFT = auto()
    BACK = auto()
    BOTTOM = auto()
    ISOMETRIC = auto()
    SECTION = auto()
    DETAIL = auto()


class DimensionType(Enum):
    """Types of dimensions."""

    LINEAR = auto()
    ANGULAR = auto()
    DIAMETER = auto()
    RADIUS = auto()


@dataclass
class DrawingView:
    """A single view in the drawing."""

    view_type: ViewType
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.view_type.name,
            "x": self.x,
            "y": self.y,
            "scale": self.scale,
        }


@dataclass
class Dimension:
    """A dimension annotation."""

    dim_type: DimensionType
    value: float
    x: float = 0.0
    y: float = 0.0
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.dim_type.name,
            "value": self.value,
            "x": self.x,
            "y": self.y,
            "text": self.text,
        }


@dataclass
class Drawing:
    """Engineering drawing."""

    title: str = ""
    sheet_size: str = "A3"
    views: list[DrawingView] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)

    def add_view(self, view: DrawingView) -> None:
        """Add a view to the drawing."""
        self.views.append(view)

    def add_dimension(self, dim: Dimension) -> None:
        """Add a dimension to the drawing."""
        self.dimensions.append(dim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "sheetSize": self.sheet_size,
            "views": [v.to_dict() for v in self.views],
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def generate_html(self) -> str:
        """Generate HTML representation of the drawing."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{self.title} - Engineering Drawing</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .drawing {{ background: white; padding: 20px; border: 1px solid #ccc; }}
        .title-block {{ border: 1px solid #000; padding: 10px; margin-bottom: 20px; }}
        .view {{ border: 1px dashed #999; padding: 10px; margin: 10px; display: inline-block; }}
        .dimension {{ color: #0066cc; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="drawing">
        <div class="title-block">
            <h1>{self.title}</h1>
            <p>Sheet: {self.sheet_size}</p>
        </div>
        <div class="views">
"""
        for view in self.views:
            html += f"""            <div class="view">
                <p><strong>{view.view_type.name}</strong> (Scale: {view.scale})</p>
                <svg width="200" height="150" style="border: 1px solid #ddd;">
                    <rect x="10" y="10" width="180" height="130" fill="none" stroke="#666"/>
                    <text x="100" y="80" text-anchor="middle" fill="#999">{view.view_type.name} VIEW</text>
                </svg>
            </div>
"""
        html += """        </div>
        <div class="dimensions">
            <h3>Dimensions</h3>
            <ul>
"""
        for dim in self.dimensions:
            html += f"""                <li class="dimension">{dim.text or f'{dim.dim_type.name}: {dim.value}'}</li>
"""
        html += """            </ul>
        </div>
    </div>
</body>
</html>"""
        return html

    def save_html(self, path: str | Path) -> None:
        """Save drawing as HTML."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate_html(), encoding="utf-8")
        logger.info("Saved drawing HTML to %s", path)


class DrawingGenerator:
    """Generates engineering drawings from SOLIDWORKS model."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def generate(
        self,
        title: str = "Engineering Drawing",
        *,
        include_views: list[ViewType] | None = None,
    ) -> Drawing:
        """Generate drawing from current model.

        Args:
            title: Drawing title.
            include_views: Views to include (default: front, top, right, iso).

        Returns:
            Drawing object.
        """
        if include_views is None:
            include_views = [
                ViewType.FRONT,
                ViewType.TOP,
                ViewType.RIGHT,
                ViewType.ISOMETRIC,
            ]

        drawing = Drawing(title=title, sheet_size="A3")

        # Add views
        x_offset = 0.0
        for view_type in include_views:
            view = DrawingView(
                view_type=view_type,
                x=x_offset,
                y=0.0,
                scale=1.0,
            )
            drawing.add_view(view)
            x_offset += 220.0

        # Add dimensions
        bbox = self._get_bounding_box()
        if bbox:
            drawing.add_dimension(Dimension(
                dim_type=DimensionType.LINEAR,
                value=bbox[0] * 1000,
                text=f"Width: {bbox[0]*1000:.1f}mm",
            ))
            drawing.add_dimension(Dimension(
                dim_type=DimensionType.LINEAR,
                value=bbox[1] * 1000,
                text=f"Height: {bbox[1]*1000:.1f}mm",
            ))
            drawing.add_dimension(Dimension(
                dim_type=DimensionType.LINEAR,
                value=bbox[2] * 1000,
                text=f"Depth: {bbox[2]*1000:.1f}mm",
            ))

        return drawing

    def _get_bounding_box(self) -> tuple[float, float, float] | None:
        return self.model.safe_size()


def generate_drawing(
    model: Any,
    title: str = "Engineering Drawing",
    *,
    output_path: str | Path | None = None,
    include_views: list[ViewType] | None = None,
) -> Drawing:
    """Convenience function to generate engineering drawing.

    Example::

        from solidworks_com import generate_drawing, ViewType

        # Generate drawing
        drawing = generate_drawing(
            part,
            title="Bracket Drawing",
            output_path="drawing.html",
            include_views=[ViewType.FRONT, ViewType.TOP, ViewType.ISOMETRIC],
        )
    """
    generator = DrawingGenerator(model)
    drawing = generator.generate(title, include_views=include_views)

    if output_path:
        drawing.save_html(output_path)

    return drawing
