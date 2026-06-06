"""Unit tests for solidworks_com.snapshot data classes (no SOLIDWORKS required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from solidworks_com.snapshot import SnapshotConfig, SnapshotResult, create_snapshot_manager


class TestSnapshotConfig:
    def test_defaults(self) -> None:
        cfg = SnapshotConfig()
        assert cfg.width == 1024
        assert cfg.height == 768
        assert cfg.format == "png"
        assert cfg.background_color == "white"

    def test_default_view_angles_populated(self) -> None:
        cfg = SnapshotConfig()
        assert cfg.view_angles is not None
        assert "iso" in cfg.view_angles

    def test_custom_angles_preserved(self) -> None:
        cfg = SnapshotConfig(view_angles=["front", "top"])
        assert cfg.view_angles == ["front", "top"]

    def test_custom_dimensions(self) -> None:
        cfg = SnapshotConfig(width=1920, height=1080)
        assert cfg.width == 1920
        assert cfg.height == 1080


class TestSnapshotResult:
    def _make_result(self, success: bool = True) -> SnapshotResult:
        return SnapshotResult(
            file_path=Path("/tmp/snap.png"),
            view_angle="iso",
            width=1024,
            height=768,
            success=success,
        )

    def test_to_dict_keys(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        for key in ("file_path", "view_angle", "width", "height", "success", "error"):
            assert key in d

    def test_success_true(self) -> None:
        r = self._make_result(success=True)
        assert r.to_dict()["success"] is True

    def test_error_none_by_default(self) -> None:
        r = self._make_result()
        assert r.error is None

    def test_error_populated(self) -> None:
        r = SnapshotResult(
            file_path=Path("/tmp/snap.png"),
            view_angle="front",
            width=1024,
            height=768,
            success=False,
            error="COM call failed",
        )
        assert r.to_dict()["error"] == "COM call failed"


class TestCreateSnapshotManager:
    def test_returns_manager(self) -> None:
        from solidworks_com.snapshot import SnapshotManager
        model = MagicMock()
        mgr = create_snapshot_manager(model)
        assert isinstance(mgr, SnapshotManager)
        assert mgr.model is model
