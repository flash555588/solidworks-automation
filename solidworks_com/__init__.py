"""Ergonomic Python wrappers for the SOLIDWORKS COM API."""

from ._version import __version__
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
from .app import SolidWorks, connect
from .auto_repair import AutoRepairLoop, RepairAction, RepairAttempt, RepairReport, execute_with_repair
from .benchmark import BenchmarkCase, BenchmarkResult, BenchmarkSuite, create_standard_benchmarks
from .bom import BOM, BOMGenerator, BOMItem, generate_bom
from .brief import BriefParser, CABBrief, parse_brief
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
from .drawing import DimensionType, Drawing, DrawingGenerator, DrawingView, ViewType, generate_drawing
from .drawing_parser import DrawingParser, ParsedDrawing, parse_drawing
from .errors import SolidWorksError
from .export import ExportFormat, ExportManager, ExportOptions, ExportResult, create_export_manager
from .geometry import Point, Vector
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
from .model import SketchContour, SketchEditor, SketchSegment
from .parameters import Parameter, ParameterManager
from .parts import PartCategory, PartsLibrary, StandardPart, create_parts_library
from .precision import (
    MeshQuality,
    MeshSettings,
    PrecisionSettings,
    PrecisionValidator,
    create_precision_validator,
)
from .repair import FailureClass, RepairAnalyzer, RepairSuggestion, analyze_error
from .repair import RepairReport as RepairReportLegacy
from .snapshot import SnapshotConfig, SnapshotManager, SnapshotResult, create_snapshot_manager
from .units import cm, deg, inch, mm
from .urdf import Joint, Link, Robot, URDFGenerator, generate_urdf
from .viewer import CADViewer, ViewerConfig, preview_step

__all__ = [
    # Core
    "SolidWorks",
    "SolidWorksError",
    "PartBuilder",
    "connect",
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
