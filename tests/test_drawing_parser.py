"""Unit tests for drawing parser module."""

from __future__ import annotations

import pytest

from solidworks_com.drawing_parser import (
    Dimension,
    DrawingParser,
    Feature,
    ParsedDrawing,
    parse_drawing,
)


class TestDimension:
    def test_creation(self) -> None:
        d = Dimension(value=100.0, unit="mm", axis="x", label="width")
        assert d.value == 100.0
        assert d.unit == "mm"
        assert d.axis == "x"

    def test_to_dict(self) -> None:
        d = Dimension(value=50.0, unit="mm", axis="y")
        result = d.to_dict()
        assert result["value"] == 50.0
        assert result["axis"] == "y"


class TestFeature:
    def test_creation(self) -> None:
        f = Feature(type="hole", diameter=4.5)
        assert f.type == "hole"
        assert f.diameter == 4.5

    def test_to_dict(self) -> None:
        f = Feature(type="fillet", radius=3.0)
        result = f.to_dict()
        assert result["type"] == "fillet"
        assert result["radius"] == 3.0


class TestParsedDrawing:
    def test_creation(self) -> None:
        d = ParsedDrawing(title="Test Drawing")
        assert d.title == "Test Drawing"
        assert len(d.views) == 0

    def test_dimensions(self) -> None:
        d = ParsedDrawing(
            title="Test",
            overall_dimensions=[
                Dimension(value=100.0, axis="x"),
                Dimension(value=60.0, axis="y"),
                Dimension(value=10.0, axis="z"),
            ],
        )
        assert d.width == 100.0
        assert d.height == 60.0
        assert d.depth == 10.0

    def test_summary(self) -> None:
        d = ParsedDrawing(
            title="Test",
            overall_dimensions=[
                Dimension(value=100.0, axis="x"),
                Dimension(value=60.0, axis="y"),
            ],
        )
        s = d.summary()
        assert "Test" in s
        assert "W=100.0mm" in s

    def test_to_dict(self) -> None:
        d = ParsedDrawing(title="Test")
        result = d.to_dict()
        assert result["title"] == "Test"
        assert "views" in result


class TestDrawingParser:
    def test_parse_text_description(self) -> None:
        parser = DrawingParser()
        drawing = parser.parse_text_description(
            "Make a 100mm by 60mm by 6mm plate with four 4.5mm holes"
        )
        assert drawing.width == 100.0
        assert drawing.height == 60.0
        assert drawing.depth == 6.0
        # Parser extracts features from text
        assert len(drawing.features) > 0

    def test_parse_text_with_fillets(self) -> None:
        parser = DrawingParser()
        drawing = parser.parse_text_description(
            "A bracket with R5 rounded corners"
        )
        assert len(drawing.features) > 0
        assert drawing.features[0].type == "fillet"
        assert drawing.features[0].radius == 5.0

    def test_parse_image_not_found(self) -> None:
        parser = DrawingParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_image("nonexistent.png")


class TestParseDrawing:
    def test_parse_with_description(self) -> None:
        drawing = parse_drawing(
            description="100mm x 60mm x 6mm plate with 4.5mm holes"
        )
        assert drawing.width == 100.0
        assert len(drawing.features) > 0

    def test_parse_no_args(self) -> None:
        with pytest.raises(ValueError):
            parse_drawing()
