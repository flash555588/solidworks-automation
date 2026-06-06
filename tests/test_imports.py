"""Basic import sanity tests for the refactored solidworks_com package.

These tests do not require a running SOLIDWORKS instance.
They verify that all modules import cleanly after the audit refactor.
"""

from __future__ import annotations


class TestCoreImports:
    def test_import_solidworks_com(self) -> None:
        import solidworks_com

        assert solidworks_com.__version__ == "0.9.0"

    def test_import_app(self) -> None:
        from solidworks_com.app import SolidWorks, connect

        assert SolidWorks is not None
        assert connect is not None

    def test_import_model(self) -> None:
        from solidworks_com.model import ModelDoc

        assert ModelDoc is not None

    def test_import_sketch(self) -> None:
        from solidworks_com.sketch import (
            SketchBuilder,
            SketchContour,
            SketchEditor,
            SketchSegment,
            _as_list,
        )

        assert SketchBuilder is not None
        assert SketchContour is not None
        assert SketchEditor is not None
        assert SketchSegment is not None

    def test_import_features(self) -> None:
        from solidworks_com.features import FeatureTools

        assert FeatureTools is not None

    def test_import_drawing_doc(self) -> None:
        from solidworks_com.drawing_doc import DrawingDoc

        assert DrawingDoc is not None

    def test_import_assembly(self) -> None:
        from solidworks_com.assembly import AssemblyDoc, Component

        assert AssemblyDoc is not None
        assert Component is not None

    def test_import_constants(self) -> None:
        from solidworks_com.constants import DocumentType, document_type_from_path

        assert DocumentType.PART == 1
        assert document_type_from_path("foo.step") == DocumentType.IMPORTED_PART

    def test_import_errors(self) -> None:
        from solidworks_com.errors import SolidWorksError

        err = SolidWorksError("test", errors=1, warnings=2)
        assert "errors=1" in str(err)

    def test_import_geometry(self) -> None:
        from solidworks_com.geometry import Point, Vector, flatten_points

        assert Point(1, 2, 3).z == 3.0
        assert flatten_points([(1, 2)]) == [1.0, 2.0, 0.0]

    def test_import_units(self) -> None:
        from solidworks_com.units import mm, cm, inch, deg

        assert mm(1000) == 1.0
        assert cm(100) == 1.0

    def test_import_builders(self) -> None:
        from solidworks_com.builders import PartBuilder

        assert PartBuilder is not None

    def test_import_com_helpers(self) -> None:
        from solidworks_com.com import (
            OutCall,
            call_member,
            call_or_value,
            member_value,
            unpack_out_call,
        )

        assert OutCall(value=1) == OutCall(value=1)

    def test_import_extension_modules(self) -> None:
        """Extension modules are lazy-loaded; just verify they resolve."""
        import solidworks_com

        # These trigger __getattr__ and actually import the sub-modules.
        assert solidworks_com.GeometryAnalyzer is not None
        assert solidworks_com.ExportManager is not None
        assert solidworks_com.ModelInspector is not None
        assert solidworks_com.ParameterManager is not None
        assert solidworks_com.MetadataManager is not None
        assert solidworks_com.PrecisionValidator is not None
        assert solidworks_com.RepairAnalyzer is not None
        assert solidworks_com.SnapshotManager is not None
        assert solidworks_com.URDFGenerator is not None
        assert solidworks_com.CADViewer is not None

    def test_repair_report_legacy_alias(self) -> None:
        """RepairReportLegacy must resolve to the same class as RepairReport."""
        import solidworks_com

        # Trigger lazy-load via __getattr__
        legacy = solidworks_com.RepairReportLegacy
        modern = solidworks_com.RepairReport
        assert legacy is modern, "RepairReportLegacy must be an alias for RepairReport"

    def test_all_exports_present(self) -> None:
        import solidworks_com

        for name in solidworks_com.__all__:
            assert hasattr(solidworks_com, name), f"{name} missing from solidworks_com"
