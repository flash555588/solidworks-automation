"""Ergonomic Python wrappers for the SOLIDWORKS COM API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._version import __version__
from .app import SolidWorks, connect
from .builders import PartBuilder
from .constants import (
    AddComponentConfigOptions,
    AddMateError,
    ChamferOption,
    ChamferType,
    ConstraintType,
    DocumentType,
    EndCondition,
    MateAlign,
    MateType,
    MoveRollbackBarTo,
    OpenDocOptions,
    PaperSize,
    RefPlaneConstraint,
    SaveAsOptions,
    SaveAsVersion,
    SelectType,
    SketchSegmentType,
    UserPreferenceStringValue,
    bitmask,
    document_type_from_path,
)
from .design_rules import (
    DesignChecker,
    DesignProfile,
    RuleSeverity,
    RuleViolation,
    validate_circle,
    validate_extrude_depth,
    validate_fillet_radius,
    validate_hole_diameter,
    validate_revolve_profile,
    validate_sketch_rectangle,
    validate_wall_thickness,
)
from .drawing_doc import DrawingDoc
from .errors import SolidWorksError
from .features import FeatureTools
from .geometry import Point, Vector
from .model import ModelDoc
from .sketch import SketchContour, SketchEditor, SketchSegment
from .units import cm, deg, inch, mm

if TYPE_CHECKING:
    # Delayed imports for type-checking only to break potential circular refs.
    from .analysis import (
        GeometryAnalyzer,
        GeometryFacts,
        GeometryValidator,
        PrecisionLevel,
        ValidationReport,
        ValidationResult,
        analyze_model,
        validate_model,
    )
    from .auto_repair import (
        AutoRepairLoop,
        RepairAction,
        RepairAttempt,
        RepairReport,
        execute_with_repair,
    )
    from .auto_repair import (
        RepairReport as RepairReportLegacy,
    )
    from .benchmark import (
        BenchmarkCase,
        BenchmarkResult,
        BenchmarkSuite,
        create_standard_benchmarks,
    )
    from .bom import BOM, BOMGenerator, BOMItem, generate_bom
    from .brief import BriefParser, CABBrief, parse_brief
    from .drawing import (
        DimensionType,
        Drawing,
        DrawingGenerator,
        DrawingView,
        ViewType,
        generate_drawing,
    )
    from .drawing_parser import DrawingParser, ParsedDrawing, parse_drawing
    from .export import ExportFormat, ExportManager, ExportOptions, ExportResult, create_export_manager
    from .inspection import BoundingBox, FeatureInfo, InspectionReport, ModelInspector
    from .manufacturing import (
        CheckResult,
        CheckSeverity,
        ManufacturingChecker,
        ManufacturingProcess,
        ManufacturingReport,
        check_manufacturing,
    )
    from .metadata import GenerationMetadata, MetadataManager, create_metadata_manager
    from .parameters import Parameter, ParameterManager
    from .parts import PartCategory, PartsLibrary, StandardPart, create_parts_library
    from .precision import (
        MeshQuality,
        MeshSettings,
        PrecisionSettings,
        PrecisionValidator,
        create_precision_validator,
    )
    from .repair import (
        FailureClass,
        RepairAnalyzer,
        RepairSuggestion,
        analyze_error,
    )
    from .snapshot import SnapshotConfig, SnapshotManager, SnapshotResult, create_snapshot_manager
    from .urdf import Joint, Link, Robot, URDFGenerator, generate_urdf
    from .viewer import CADViewer, ViewerConfig, preview_step


# Lazy-load extension modules via __getattr__ to avoid circular imports
# and heavy import-time side effects.
_EXTENSION_MODULES: dict[str, tuple[str, ...]] = {
    "analysis": (
        "GeometryAnalyzer", "GeometryFacts", "GeometryValidator",
        "PrecisionLevel", "ValidationReport", "ValidationResult",
        "analyze_model", "validate_model",
    ),
    "auto_repair": (
        "AutoRepairLoop", "RepairAction", "RepairAttempt", "RepairReport",
        "RepairReportLegacy", "execute_with_repair",
    ),
    "benchmark": (
        "BenchmarkCase", "BenchmarkResult", "BenchmarkSuite", "create_standard_benchmarks",
    ),
    "bom": ("BOM", "BOMGenerator", "BOMItem", "generate_bom"),
    "brief": ("BriefParser", "CABBrief", "parse_brief"),
    "drawing": (
        "Drawing", "DrawingGenerator", "DrawingView", "DimensionType",
        "ViewType", "generate_drawing",
    ),
    "drawing_parser": ("DrawingParser", "ParsedDrawing", "parse_drawing"),
    "export": ("ExportFormat", "ExportManager", "ExportOptions", "ExportResult", "create_export_manager"),
    "inspection": ("BoundingBox", "FeatureInfo", "InspectionReport", "ModelInspector"),
    "manufacturing": (
        "CheckResult", "CheckSeverity", "ManufacturingChecker",
        "ManufacturingProcess", "ManufacturingReport", "check_manufacturing",
    ),
    "metadata": ("GenerationMetadata", "MetadataManager", "create_metadata_manager"),
    "parameters": ("Parameter", "ParameterManager"),
    "parts": ("PartCategory", "PartsLibrary", "StandardPart", "create_parts_library"),
    "precision": (
        "MeshQuality", "MeshSettings", "PrecisionSettings",
        "PrecisionValidator", "create_precision_validator",
    ),
    "repair": (
        "FailureClass", "RepairAnalyzer",
        "RepairSuggestion", "analyze_error",
    ),
    "snapshot": ("SnapshotConfig", "SnapshotManager", "SnapshotResult", "create_snapshot_manager"),
    "urdf": ("Joint", "Link", "Robot", "URDFGenerator", "generate_urdf"),
    "viewer": ("CADViewer", "ViewerConfig", "preview_step"),
}

_NAME_TO_MODULE: dict[str, str] = {}
for _mod, _names in _EXTENSION_MODULES.items():
    for _n in _names:
        _NAME_TO_MODULE[_n] = _mod


def __getattr__(name: str) -> object:
    """Lazy-load extension symbols on first access."""
    mod_name = _NAME_TO_MODULE.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod = __import__(f"{__name__}.{mod_name}", fromlist=[name])
    return getattr(mod, name)


__all__ = [
    # Core
    "SolidWorks",
    "SolidWorksError",
    "PartBuilder",
    "connect",
    # Design rules
    "DesignChecker",
    "DesignProfile",
    "RuleSeverity",
    "RuleViolation",
    "validate_revolve_profile",
    "validate_extrude_depth",
    "validate_wall_thickness",
    "validate_hole_diameter",
    "validate_fillet_radius",
    "validate_sketch_rectangle",
    "validate_circle",
    # Analysis
    "GeometryAnalyzer",
    "GeometryFacts",
    "GeometryValidator",
    "PrecisionLevel",
    "ValidationReport",
    "ValidationResult",
    "analyze_model",
    "validate_model",
    # Auto Repair
    "AutoRepairLoop",
    "RepairAction",
    "RepairAttempt",
    "RepairReport",
    "execute_with_repair",
    # Benchmark
    "BenchmarkCase",
    "BenchmarkResult",
    "BenchmarkSuite",
    "create_standard_benchmarks",
    # BOM
    "BOM",
    "BOMGenerator",
    "BOMItem",
    "generate_bom",
    # Brief
    "BriefParser",
    "CABBrief",
    "parse_brief",
    # Constants
    "AddComponentConfigOptions",
    "AddMateError",
    "ChamferOption",
    "ChamferType",
    "ConstraintType",
    "DocumentType",
    "EndCondition",
    "MateAlign",
    "MateType",
    "MoveRollbackBarTo",
    "OpenDocOptions",
    "PaperSize",
    "RefPlaneConstraint",
    "SaveAsOptions",
    "SaveAsVersion",
    "SelectType",
    "SketchSegmentType",
    "UserPreferenceStringValue",
    "bitmask",
    "document_type_from_path",
    # Drawing Doc
    "DrawingDoc",
    # Drawing
    "Drawing",
    "DrawingGenerator",
    "DrawingView",
    "DimensionType",
    "ViewType",
    "generate_drawing",
    # Drawing Parser
    "DrawingParser",
    "ParsedDrawing",
    "parse_drawing",
    # Export
    "ExportFormat",
    "ExportManager",
    "ExportOptions",
    "ExportResult",
    "create_export_manager",
    # Features
    "FeatureTools",
    # Geometry
    "Point",
    "Vector",
    # Inspection
    "BoundingBox",
    "FeatureInfo",
    "InspectionReport",
    "ModelInspector",
    # Manufacturing
    "CheckResult",
    "CheckSeverity",
    "ManufacturingChecker",
    "ManufacturingProcess",
    "ManufacturingReport",
    "check_manufacturing",
    # Metadata
    "GenerationMetadata",
    "MetadataManager",
    "create_metadata_manager",
    # Model
    "ModelDoc",
    "SketchContour",
    "SketchEditor",
    "SketchSegment",
    # Parameters
    "Parameter",
    "ParameterManager",
    # Parts
    "PartCategory",
    "PartsLibrary",
    "StandardPart",
    "create_parts_library",
    # Precision
    "MeshQuality",
    "MeshSettings",
    "PrecisionSettings",
    "PrecisionValidator",
    "create_precision_validator",
    # Repair
    "FailureClass",
    "RepairAnalyzer",
    "RepairReportLegacy",
    "RepairSuggestion",
    "analyze_error",
    # Snapshot
    "SnapshotConfig",
    "SnapshotManager",
    "SnapshotResult",
    "create_snapshot_manager",
    # Units
    "mm",
    "cm",
    "inch",
    "deg",
    # URDF
    "Joint",
    "Link",
    "Robot",
    "URDFGenerator",
    "generate_urdf",
    # Viewer
    "CADViewer",
    "ViewerConfig",
    "preview_step",
    "__version__",
]
