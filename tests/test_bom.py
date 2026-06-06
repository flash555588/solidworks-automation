"""Unit tests for solidworks_com.bom (no SOLIDWORKS required)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from solidworks_com.bom import BOM, BOMGenerator, BOMItem


class TestBOMItem:
    def test_total_cost_auto_calculated(self) -> None:
        item = BOMItem(1, "P-001", "Bolt", 10, unit_cost=0.5)
        assert item.total_cost == pytest.approx(5.0)

    def test_explicit_total_cost_not_overridden(self) -> None:
        item = BOMItem(1, "P-001", "Bolt", 10, unit_cost=0.5, total_cost=99.0)
        assert item.total_cost == pytest.approx(99.0)

    def test_to_dict_keys(self) -> None:
        item = BOMItem(1, "P-001", "Bolt", 2)
        d = item.to_dict()
        for key in ("itemNumber", "partNumber", "description", "quantity"):
            assert key in d


class TestBOM:
    def _make_bom(self) -> BOM:
        bom = BOM(project_name="Test project", revision="B")
        bom.add_item(BOMItem(1, "P-001", "Hex bolt M3", 10, unit_cost=0.20))
        bom.add_item(BOMItem(2, "P-002", "Washer M3",   20, unit_cost=0.05))
        return bom

    def test_total_items(self) -> None:
        bom = self._make_bom()
        assert bom.total_items == 2

    def test_total_quantity(self) -> None:
        bom = self._make_bom()
        assert bom.total_quantity == 30

    def test_total_cost(self) -> None:
        bom = self._make_bom()
        assert bom.total_cost == pytest.approx(10 * 0.20 + 20 * 0.05)

    def test_to_csv_has_header(self) -> None:
        bom = self._make_bom()
        csv_text = bom.to_csv()
        assert "Part Number" in csv_text or "Item" in csv_text

    def test_to_csv_contains_part_numbers(self) -> None:
        bom = self._make_bom()
        csv_text = bom.to_csv()
        assert "P-001" in csv_text
        assert "P-002" in csv_text

    def test_to_csv_is_valid_csv(self) -> None:
        bom = self._make_bom()
        csv_text = bom.to_csv()
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Header + 2 data rows + totals row = 4
        assert len(rows) >= 3

    def test_save_csv(self, tmp_path: Path) -> None:
        bom = self._make_bom()
        out = tmp_path / "bom.csv"
        bom.save_csv(out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "P-001" in content

    def test_to_dict_structure(self) -> None:
        bom = self._make_bom()
        d = bom.to_dict()
        assert d["project"] == "Test project"
        assert d["revision"] == "B"
        assert "items" in d
        assert len(d["items"]) == 2

    def test_empty_bom(self) -> None:
        bom = BOM()
        assert bom.total_items == 0
        assert bom.total_cost == 0.0
        csv_text = bom.to_csv()
        assert csv_text != ""


class TestBOMGenerator:
    def test_instantiation_with_mock(self) -> None:
        """BOMGenerator should store the model without COM calls."""
        from unittest.mock import MagicMock
        model = MagicMock()
        gen = BOMGenerator(model)
        assert gen.model is model
