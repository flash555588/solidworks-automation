"""Unit tests for viewer and parts modules."""

from __future__ import annotations

from solidworks_com.parts import PartCategory, PartsLibrary, PartStandard, StandardPart
from solidworks_com.viewer import CADViewer, ViewerConfig


class TestViewerConfig:
    def test_defaults(self) -> None:
        c = ViewerConfig()
        assert c.width == 800
        assert c.height == 600
        assert c.grid_visible is True

    def test_to_dict(self) -> None:
        c = ViewerConfig()
        d = c.to_dict()
        assert d["width"] == 800
        assert d["gridVisible"] is True


class TestCADViewer:
    def test_generate_html(self) -> None:
        v = CADViewer()
        html = v.generate_html("test_model")
        assert "test_model" in html
        assert "three" in html.lower()

    def test_preview_file_not_found(self) -> None:
        import pytest
        v = CADViewer()
        with pytest.raises(FileNotFoundError):
            v.preview("nonexistent.step")


class TestPartCategory:
    def test_values(self) -> None:
        assert PartCategory.SCREW.name == "SCREW"
        assert PartCategory.BEARING.name == "BEARING"


class TestStandardPart:
    def test_creation(self) -> None:
        p = StandardPart(
            name="M6 Screw",
            category=PartCategory.SCREW,
            standard=PartStandard.ISO,
            size="M6",
            description="Socket head cap screw",
        )
        assert p.name == "M6 Screw"
        assert p.size == "M6"

    def test_to_dict(self) -> None:
        p = StandardPart(
            name="M6 Screw",
            category=PartCategory.SCREW,
            standard=PartStandard.ISO,
            size="M6",
            description="Socket head cap screw",
            dimensions={"diameter": 0.006},
        )
        d = p.to_dict()
        assert d["name"] == "M6 Screw"
        assert d["dimensions"]["diameter"] == 0.006


class TestPartsLibrary:
    def test_creation(self) -> None:
        lib = PartsLibrary()
        assert len(lib._parts) > 0

    def test_search(self) -> None:
        lib = PartsLibrary()
        results = lib.search("M6")
        assert len(results) > 0
        assert any("M6" in p.size for p in results)

    def test_search_by_category(self) -> None:
        lib = PartsLibrary()
        results = lib.search("screw", category=PartCategory.SCREW)
        assert all(p.category == PartCategory.SCREW for p in results)

    def test_get_screw(self) -> None:
        lib = PartsLibrary()
        screw = lib.get_screw("M6", 0.020)
        assert screw is not None
        assert "M6" in screw.name
        assert screw.dimensions["length"] == 0.020

    def test_list_parts(self) -> None:
        lib = PartsLibrary()
        parts = lib.list_parts()
        assert len(parts) > 0

    def test_list_by_category(self) -> None:
        lib = PartsLibrary()
        screws = lib.list_parts(category=PartCategory.SCREW)
        assert all(p.category == PartCategory.SCREW for p in screws)

    def test_add_part(self) -> None:
        lib = PartsLibrary()
        initial_count = len(lib._parts)
        lib.add_part(StandardPart(
            name="Custom Part",
            category=PartCategory.CONNECTOR,
            standard=PartStandard.ISO,
            size="CUSTOM",
            description="A custom part",
        ))
        assert len(lib._parts) == initial_count + 1


class TestCreatePartsLibrary:
    def test_create(self) -> None:
        from solidworks_com import create_parts_library
        lib = create_parts_library()
        assert len(lib._parts) > 0
