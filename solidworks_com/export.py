"""Multi-format export support.

Inspired by text-to-cad's export capabilities:
- STEP (primary format)
- STL (3D printing)
- 3MF (3D printing with metadata)
- IGES (legacy CAD exchange)
- DXF (2D drawings)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats."""

    STEP = auto()
    STP = auto()
    STL = auto()
    THREE_MF = auto()
    IGES = auto()
    IGS = auto()
    DXF = auto()
    DWG = auto()
    PARASOLID = auto()
    VRML = auto()

    @property
    def extension(self) -> str:
        """Get the file extension for this format."""
        extensions = {
            ExportFormat.STEP: ".step",
            ExportFormat.STP: ".stp",
            ExportFormat.STL: ".stl",
            ExportFormat.THREE_MF: ".3mf",
            ExportFormat.IGES: ".iges",
            ExportFormat.IGS: ".igs",
            ExportFormat.DXF: ".dxf",
            ExportFormat.DWG: ".dwg",
            ExportFormat.PARASOLID: ".x_t",
            ExportFormat.VRML: ".wrl",
        }
        return extensions[self]

    @property
    def description(self) -> str:
        """Get a human-readable description of this format."""
        descriptions = {
            ExportFormat.STEP: "STEP (Standard for the Exchange of Product Data)",
            ExportFormat.STP: "STP (STEP variant)",
            ExportFormat.STL: "STL (Standard Triangle Language)",
            ExportFormat.THREE_MF: "3MF (3D Manufacturing Format)",
            ExportFormat.IGES: "IGES (Initial Graphics Exchange Specification)",
            ExportFormat.IGS: "IGS (IGES variant)",
            ExportFormat.DXF: "DXF (Drawing Exchange Format)",
            ExportFormat.DWG: "DWG (Drawing)",
            ExportFormat.PARASOLID: "Parasolid (XT)",
            ExportFormat.VRML: "VRML (Virtual Reality Modeling Language)",
        }
        return descriptions[self]


@dataclass
class ExportOptions:
    """Options for export operations."""

    format: ExportFormat
    output_path: Path | None = None

    # Format-specific options
    stl_resolution: float = 0.01  # mm
    stl_ascii: bool = False
    step_version: str = "AP214"
    dxf_version: str = "R2013"

    # General options
    include_metadata: bool = True
    overwrite: bool = False


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    format: ExportFormat
    output_path: Path | None = None
    file_size_bytes: int | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "format": self.format.name,
            "output_path": str(self.output_path) if self.output_path else None,
            "file_size_bytes": self.file_size_bytes,
            "error_message": self.error_message,
        }


class ExportManager:
    """Manages model export to multiple formats."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def export(
        self,
        format: ExportFormat | str,
        output_path: str | Path | None = None,
        **kwargs: Any,
    ) -> ExportResult:
        """Export the model to the specified format.

        Args:
            format: Target export format.
            output_path: Output file path. If None, auto-generates from model name.
            **kwargs: Additional format-specific options.

        Returns:
            ExportResult with the export details.
        """
        # Resolve format
        if isinstance(format, str):
            format = self._resolve_format(format)

        # Generate output path if not provided; resolve to absolute path
        output_path = self._generate_output_path(format) if output_path is None else Path(output_path).resolve()

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists and overwrite is disabled
        if output_path.exists() and not kwargs.get('overwrite', False):
            logger.warning("Output file already exists: %s", output_path)

        try:
            # Perform the export
            self._do_export(format, output_path, **kwargs)

            # Get file size
            file_size = output_path.stat().st_size if output_path.exists() else None

            return ExportResult(
                success=True,
                format=format,
                output_path=output_path,
                file_size_bytes=file_size,
            )

        except Exception as e:
            logger.error("Export failed: %s", e)
            return ExportResult(
                success=False,
                format=format,
                output_path=output_path,
                error_message=str(e),
            )

    def export_multiple(
        self,
        formats: list[ExportFormat | str],
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> list[ExportResult]:
        """Export the model to multiple formats.

        Args:
            formats: List of target export formats.
            output_dir: Output directory. If None, uses current directory.
            **kwargs: Additional format-specific options.

        Returns:
            List of ExportResult for each format.
        """
        output_dir = Path.cwd() if output_dir is None else Path(output_dir)

        results = []
        for fmt in formats:
            if isinstance(fmt, str):
                fmt = self._resolve_format(fmt)

            output_path = output_dir / f"{self._get_model_name()}{fmt.extension}"
            result = self.export(fmt, output_path, **kwargs)
            results.append(result)

        return results

    def _do_export(self, format: ExportFormat, output_path: Path, **kwargs: Any) -> None:
        """Perform the actual export with format-specific options."""
        try:
            # Activate and clear selection before export
            self.model.activate()
            self.model.clear_selection()

            # Build format-specific export data when possible.
            export_data = self._build_export_data(format, **kwargs)
            self.model.save_as(output_path, export_data=export_data)

        except Exception as e:
            raise SolidWorksExportError(f"Failed to export to {format.name}: {e}") from e

    def _build_export_data(self, format: ExportFormat, **kwargs: Any) -> Any:
        """Create a format-specific export-data COM object if available."""
        from .com import empty_dispatch, import_pywin32

        _, win32com_client = import_pywin32()

        # Map formats to their SOLIDWORKS export-data ProgIDs / creation paths.
        # These vary by SOLIDWORKS version; we gracefully fall back to None.
        prog_id_map: dict[ExportFormat, str] = {
            ExportFormat.STEP: "SldWorks.STEPExportData",
            ExportFormat.STP: "SldWorks.STEPExportData",
            ExportFormat.IGES: "SldWorks.IGESExportData",
            ExportFormat.IGS: "SldWorks.IGESExportData",
            ExportFormat.STL: "SldWorks.STLExportData",
            ExportFormat.THREE_MF: "SldWorks._3MFExportData",
        }

        prog_id = prog_id_map.get(format)
        if prog_id is None:
            return empty_dispatch()

        try:
            data = win32com_client.Dispatch(prog_id)
        except Exception as e:
            logger.debug("Failed to create export data object %r: %s", prog_id, e)
            return empty_dispatch()

        # Apply format-specific settings when the API exposes them.
        if format in (ExportFormat.STEP, ExportFormat.STP):
            step_version = kwargs.get("step_version", "AP214")
            if hasattr(data, "SetProtocol"):
                data.SetProtocol(step_version)
        elif format in (ExportFormat.STL,):
            stl_ascii = kwargs.get("stl_ascii", False)
            stl_resolution = kwargs.get("stl_resolution", 0.01)
            if hasattr(data, "SetOption"):
                data.SetOption(0, not stl_ascii)  # 0 = binary flag (vendor-specific)
            if hasattr(data, "SetResolution"):
                data.SetResolution(float(stl_resolution))

        return data

    def _resolve_format(self, format_str: str) -> ExportFormat:
        """Resolve a format string to ExportFormat."""
        format_lower = format_str.lower().strip('.')

        format_map = {
            'step': ExportFormat.STEP,
            'stp': ExportFormat.STP,
            'stl': ExportFormat.STL,
            '3mf': ExportFormat.THREE_MF,
            'iges': ExportFormat.IGES,
            'igs': ExportFormat.IGS,
            'dxf': ExportFormat.DXF,
            'dwg': ExportFormat.DWG,
            'x_t': ExportFormat.PARASOLID,
            'wrl': ExportFormat.VRML,
        }

        if format_lower not in format_map:
            raise ValueError(f"Unsupported format: {format_str}")

        return format_map[format_lower]

    def _generate_output_path(self, format: ExportFormat) -> Path:
        """Generate an output path based on model name."""
        model_name = self._get_model_name()
        return Path.cwd() / f"{model_name}{format.extension}"

    def _get_model_name(self) -> str:
        """Get the model name for file naming."""
        try:
            title = self.model.title
            return Path(title).stem if title else "model"
        except Exception as e:
            logger.debug("Failed to get model name: %s", e)
            return "model"


class SolidWorksExportError(Exception):
    """Exception raised for export failures."""
    pass


def create_export_manager(model: Any) -> ExportManager:
    """Create an ExportManager for the given model.

    Example::

        manager = create_export_manager(part)

        # Export to single format
        result = manager.export("step", "output/model.step")
        if result.success:
            print(f"Exported to {result.output_path}")

        # Export to multiple formats
        results = manager.export_multiple(["step", "stl"], "output/")
        for r in results:
            if r.success:
                print(f"Exported to {r.format.name}: {r.output_path}")
    """
    return ExportManager(model)
