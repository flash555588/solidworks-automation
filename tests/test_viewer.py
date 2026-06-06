"""Unit tests for solidworks_com.viewer (no SOLIDWORKS required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_com.viewer import CADViewer, ViewerConfig, preview_step


class TestViewerConfig:
    def test_defaults(self) -> None:
        cfg = ViewerConfig()
        assert cfg.width == 800
        assert cfg.height == 600
        assert cfg.grid_visible is True
        assert cfg.axes_visible is True
        assert cfg.auto_rotate is False

    def test_to_dict(self) -> None:
        cfg = ViewerConfig(width=1024, height=768, auto_rotate=True)
        d = cfg.to_dict()
        assert d["width"] == 1024
        assert d["autoRotate"] is True


class TestCADViewer:
    def test_generate_html_without_stl(self) -> None:
        viewer = CADViewer()
        html = viewer.generate_html("test_model")
        assert "<!DOCTYPE html>" in html
        assert "test_model" in html
        assert "three" in html.lower() or "THREE" in html

    def test_generate_html_contains_drop_hint(self) -> None:
        viewer = CADViewer()
        html = viewer.generate_html("model")
        assert "Drop" in html or "drop" in html

    def test_generate_html_no_base64_when_no_stl(self) -> None:
        viewer = CADViewer()
        html = viewer.generate_html("model")
        # B64_STL should be empty string
        assert 'const B64_STL = ""' in html

    def test_generate_html_embeds_stl(self, tmp_path: Path) -> None:
        # Create a minimal valid binary STL (84-byte header + 0 triangles)
        stl_data = b"SOLIDWORKS binary STL test" + b"\x00" * 58 + b"\x00\x00\x00\x00"
        stl_file = tmp_path / "test.stl"
        stl_file.write_bytes(stl_data)

        viewer = CADViewer()
        html = viewer.generate_html("model", stl_path=stl_file)
        # Non-empty base64 should be embedded
        assert 'const B64_STL = ""' not in html
        assert "B64_STL" in html

    def test_generate_html_auto_detects_sibling_stl(self, tmp_path: Path) -> None:
        stl_data = b"STL" + b"\x00" * 81
        step_file = tmp_path / "part.step"
        stl_file  = tmp_path / "part.stl"
        step_file.write_text("placeholder")
        stl_file.write_bytes(stl_data)

        viewer = CADViewer()
        html = viewer.generate_html("part", step_path=step_file)
        assert 'const B64_STL = ""' not in html

    def test_generate_html_no_stl_if_step_sibling_missing(self, tmp_path: Path) -> None:
        step_file = tmp_path / "part.step"
        step_file.write_text("placeholder")

        viewer = CADViewer()
        html = viewer.generate_html("part", step_path=step_file)
        assert 'const B64_STL = ""' in html

    def test_preview_raises_for_missing_file(self, tmp_path: Path) -> None:
        viewer = CADViewer()
        with pytest.raises(FileNotFoundError):
            viewer.preview(tmp_path / "nonexistent.step", open_browser=False)

    def test_preview_creates_html_file(self, tmp_path: Path) -> None:
        step_file = tmp_path / "part.step"
        step_file.write_text("placeholder")

        viewer = CADViewer()
        html_path = viewer.preview(step_file, open_browser=False)
        assert html_path.exists()
        assert html_path.suffix == ".html"
        content = html_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_config_affects_html(self) -> None:
        cfg = ViewerConfig(background_color="#abcdef", grid_visible=False)
        viewer = CADViewer(config=cfg)
        html = viewer.generate_html("model")
        assert "#abcdef" in html
        assert "false" in html   # grid_visible=False → 'false' in JS


class TestPreviewStep:
    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            preview_step(tmp_path / "nope.step", open_browser=False)
