"""Bill of Materials (BOM) generator.

Generates BOM from assembly models for:
- Manufacturing planning
- Cost estimation
- Inventory management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BOMItem:
    """Single item in Bill of Materials."""

    item_number: int
    part_number: str
    description: str
    quantity: int
    material: str = ""
    unit_cost: float = 0.0
    total_cost: float = 0.0
    supplier: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.total_cost == 0.0 and self.unit_cost > 0:
            self.total_cost = self.unit_cost * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "itemNumber": self.item_number,
            "partNumber": self.part_number,
            "description": self.description,
            "quantity": self.quantity,
            "material": self.material,
            "unitCost": self.unit_cost,
            "totalCost": self.total_cost,
            "supplier": self.supplier,
            "notes": self.notes,
        }


@dataclass
class BOM:
    """Bill of Materials."""

    project_name: str = ""
    revision: str = "A"
    date: str = ""
    items: list[BOMItem] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def total_cost(self) -> float:
        return sum(item.total_cost for item in self.items)

    def add_item(self, item: BOMItem) -> None:
        """Add an item to the BOM."""
        self.items.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project_name,
            "revision": self.revision,
            "date": self.date,
            "items": [item.to_dict() for item in self.items],
            "summary": {
                "totalItems": self.total_items,
                "totalQuantity": self.total_quantity,
                "totalCost": self.total_cost,
            },
        }

    def to_csv(self) -> str:
        """Generate CSV string using the standard library csv module."""
        import csv
        import io

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Item", "Part Number", "Description", "Qty", "Material",
            "Unit Cost", "Total", "Supplier", "Notes",
        ])
        for item in self.items:
            writer.writerow([
                item.item_number,
                item.part_number,
                item.description,
                item.quantity,
                item.material,
                f"${item.unit_cost:.2f}",
                f"${item.total_cost:.2f}",
                item.supplier,
                item.notes,
            ])
        writer.writerow([
            "", "", "", "", "", "", f"${self.total_cost:.2f}", "", "",
        ])
        return output.getvalue()

    def save_csv(self, path: str | Path) -> None:
        """Save BOM to CSV file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_csv(), encoding="utf-8")
        logger.info("Saved BOM to %s", path)

    def save_html(self, path: str | Path) -> None:
        """Save BOM to HTML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>BOM - {self.project_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .total {{ font-weight: bold; background-color: #e8f5e9; }}
    </style>
</head>
<body>
    <h1>Bill of Materials</h1>
    <p><strong>Project:</strong> {self.project_name}</p>
    <p><strong>Revision:</strong> {self.revision}</p>
    <p><strong>Date:</strong> {self.date}</p>
    <table>
        <tr>
            <th>Item</th>
            <th>Part Number</th>
            <th>Description</th>
            <th>Qty</th>
            <th>Material</th>
            <th>Unit Cost</th>
            <th>Total</th>
            <th>Supplier</th>
            <th>Notes</th>
        </tr>
"""
        for item in self.items:
            html += f"""        <tr>
            <td>{item.item_number}</td>
            <td>{item.part_number}</td>
            <td>{item.description}</td>
            <td>{item.quantity}</td>
            <td>{item.material}</td>
            <td>${item.unit_cost:.2f}</td>
            <td>${item.total_cost:.2f}</td>
            <td>{item.supplier}</td>
            <td>{item.notes}</td>
        </tr>
"""
        html += f"""        <tr class="total">
            <td colspan="6">Total</td>
            <td>${self.total_cost:.2f}</td>
            <td colspan="2"></td>
        </tr>
    </table>
</body>
</html>"""
        path.write_text(html, encoding="utf-8")
        logger.info("Saved BOM HTML to %s", path)


class BOMGenerator:
    """Generates BOM from SOLIDWORKS assembly."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def generate(self, project_name: str = "Project") -> BOM:
        """Generate BOM from current model.

        Args:
            project_name: Name of the project.

        Returns:
            BOM object with components.
        """
        bom = BOM(
            project_name=project_name,
            revision="A",
        )

        # Get components
        components = self._get_components()

        for i, comp in enumerate(components, 1):
            bom.add_item(BOMItem(
                item_number=i,
                part_number=comp.get("name", f"PART-{i:03d}"),
                description=comp.get("description", ""),
                quantity=comp.get("quantity", 1),
                material=comp.get("material", ""),
            ))

        return bom

    def _get_components(self) -> list[dict[str, Any]]:
        """Get assembly components."""
        components = []
        try:
            # Try to get components from assembly
            if hasattr(self.model.com, 'GetComponents'):
                comps = self.model.com.GetComponents()
                if comps:
                    for comp in comps:
                        name = getattr(comp, 'Name2', 'Unknown')
                        components.append({
                            "name": name,
                            "description": name,
                            "quantity": 1,
                        })
        except Exception as e:
            logger.debug("Failed to get components: %s", e)

        # If no components found, add the model itself
        if not components:
            components.append({
                "name": self.model.title,
                "description": "Main part",
                "quantity": 1,
            })

        return components


def generate_bom(
    model: Any,
    project_name: str = "Project",
    *,
    output_csv: str | Path | None = None,
    output_html: str | Path | None = None,
) -> BOM:
    """Convenience function to generate BOM.

    Example::

        from solidworks_com import generate_bom

        # Generate BOM
        bom = generate_bom(
            assembly,
            project_name="Robot Arm",
            output_csv="bom.csv",
            output_html="bom.html",
        )
    """
    generator = BOMGenerator(model)
    bom = generator.generate(project_name)

    if output_csv:
        bom.save_csv(output_csv)
    if output_html:
        bom.save_html(output_html)

    return bom
