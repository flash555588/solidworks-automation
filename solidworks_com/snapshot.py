"""Snapshot and visual verification for SOLIDWORKS models.

Inspired by text-to-cad's snapshot-review principles:
- Use PNGs for static reviews
- Use GIFs for motion/animation reviews
- Always verify visible geometry with snapshots
- Skip only when no visible geometry changed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SnapshotConfig:
    """Configuration for model snapshots."""

    width: int = 1024
    height: int = 768
    format: str = "png"  # png, jpg, bmp
    background_color: str = "white"
    view_angles: list[str] | None = None  # front, back, left, right, top, bottom, iso

    def __post_init__(self) -> None:
        if self.view_angles is None:
            self.view_angles = ["iso"]


@dataclass
class SnapshotResult:
    """Result of a snapshot operation."""

    file_path: Path
    view_angle: str
    width: int
    height: int
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "view_angle": self.view_angle,
            "width": self.width,
            "height": self.height,
            "success": self.success,
            "error": self.error,
        }


class SnapshotManager:
    """Manages model snapshots for visual verification."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def take_snapshot(
        self,
        output_path: str | Path,
        *,
        config: SnapshotConfig | None = None,
        view_angle: str = "iso",
    ) -> SnapshotResult:
        """Take a snapshot of the current model view.

        Args:
            output_path: Path to save the snapshot.
            config: Snapshot configuration.
            view_angle: View angle (front, back, left, right, top, bottom, iso).

        Returns:
            SnapshotResult with the snapshot details.
        """
        if config is None:
            config = SnapshotConfig()

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Set view angle
            self._set_view_angle(view_angle)

            # Set background color
            self._set_background(config.background_color)

            # Export the view
            success = self._export_view(output, config.width, config.height, config.format)

            if success:
                return SnapshotResult(
                    file_path=output,
                    view_angle=view_angle,
                    width=config.width,
                    height=config.height,
                    success=True,
                )
            else:
                return SnapshotResult(
                    file_path=output,
                    view_angle=view_angle,
                    width=config.width,
                    height=config.height,
                    success=False,
                    error="Export failed",
                )

        except Exception as e:
            logger.error("Snapshot failed: %s", e)
            return SnapshotResult(
                file_path=output,
                view_angle=view_angle,
                width=config.width,
                height=config.height,
                success=False,
                error=str(e),
            )

    def take_multi_view_snapshots(
        self,
        output_dir: str | Path,
        *,
        config: SnapshotConfig | None = None,
        views: list[str] | None = None,
    ) -> list[SnapshotResult]:
        """Take snapshots from multiple view angles.

        Args:
            output_dir: Directory to save snapshots.
            config: Snapshot configuration.
            views: List of view angles. Defaults to ["front", "right", "top", "iso"].

        Returns:
            List of SnapshotResult for each view.
        """
        if config is None:
            config = SnapshotConfig()
        if views is None:
            views = ["front", "right", "top", "iso"]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        model_name = self._get_model_name()

        for view in views:
            filename = f"{model_name}_{view}.{config.format}"
            output_path = output_dir / filename
            result = self.take_snapshot(output_path, config=config, view_angle=view)
            results.append(result)

        return results

    def _set_view_angle(self, angle: str) -> None:
        """Set the view angle of the model."""
        try:
            view = self.model.com.ActiveView
            if view is None:
                return

            angle_lower = angle.lower()

            if angle_lower == "front":
                view.ViewOrientation = 1  # swViewOrientation_Front
            elif angle_lower == "back":
                view.ViewOrientation = 2  # swViewOrientation_Back
            elif angle_lower == "left":
                view.ViewOrientation = 3  # swViewOrientation_Left
            elif angle_lower == "right":
                view.ViewOrientation = 4  # swViewOrientation_Right
            elif angle_lower == "top":
                view.ViewOrientation = 5  # swViewOrientation_Top
            elif angle_lower == "bottom":
                view.ViewOrientation = 6  # swViewOrientation_Bottom
            elif angle_lower == "iso":
                view.ViewOrientation = 7  # swViewOrientation_Isometric
            elif angle_lower == "dimetric":
                view.ViewOrientation = 8  # swViewOrientation_Dimetric
            elif angle_lower == "trimetric":
                view.ViewOrientation = 9  # swViewOrientation_Trimetric

            # Force view update
            view.ZoomToFit2()

        except (AttributeError, TypeError) as e:
            logger.debug("Failed to set view angle: %s", e)

    def _set_background(self, color: str) -> None:
        """Set the background color."""
        try:
            # SOLIDWORKS background colors (simplified)
            # This would need proper implementation based on SW API
            pass
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to set background: %s", e)

    def _export_view(self, output_path: Path, width: int, height: int, format: str) -> bool:
        """Export the current view to a file.

        .. warning::
            This method is a placeholder. Actual image export via the
            SOLIDWORKS API is not yet implemented.
        """
        import warnings
        warnings.warn(
            "SnapshotManager._export_view is not fully implemented. "
            "Snapshots will not be saved to disk.",
            UserWarning,
            stacklevel=2,
        )
        try:
            # Use SOLIDWORKS SaveAs for image export
            # This is a simplified version - actual implementation would use
            # IModelDoc2::SaveAs with appropriate options
            return False
        except (AttributeError, TypeError) as e:
            logger.error("Export failed: %s", e)
            return False

    def _get_model_name(self) -> str:
        """Get the model name for file naming."""
        try:
            title = self.model.title
            return Path(title).stem if title else "model"
        except Exception as e:
            logger.debug("Failed to get model name: %s", e)
            return "model"


def create_snapshot_manager(model: Any) -> SnapshotManager:
    """Create a SnapshotManager for the given model.

    Example::

        manager = create_snapshot_manager(part)

        # Single snapshot
        result = manager.take_snapshot("output/front_view.png", view_angle="front")

        # Multiple views
        results = manager.take_multi_view_snapshots("output/snapshots/")
        for r in results:
            if r.success:
                print(f"Saved: {r.file_path}")
    """
    return SnapshotManager(model)
