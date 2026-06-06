"""Unit tests for solidworks_com.constants."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_com.constants import (
    AddMateError,
    DocumentType,
    EndCondition,
    MateAlign,
    MateType,
    SaveAsVersion,
    SelectType,
    bitmask,
    document_type_from_path,
)


class TestBitmask:
    def test_no_flags(self) -> None:
        assert bitmask() == 0

    def test_single_int(self) -> None:
        assert bitmask(1) == 1
        assert bitmask(8) == 8

    def test_multiple_ints(self) -> None:
        assert bitmask(1, 2, 4) == 7

    def test_enum_flags(self) -> None:
        # SaveAsOptions.Silent == 1, .ExportTo2DPdfFromInspection == 2048
        result = bitmask(1, 2048)
        assert result == 2049


class TestDocumentTypeFromPath:
    @pytest.mark.parametrize(
        "path, expected",
        [
            ("foo.SLDPRT", DocumentType.PART),
            ("foo.sldprt", DocumentType.PART),
            ("foo.SLDASM", DocumentType.ASSEMBLY),
            ("foo.sldasm", DocumentType.ASSEMBLY),
            ("foo.SLDDRW", DocumentType.DRAWING),
            ("foo.slddrw", DocumentType.DRAWING),
        ],
    )
    def test_known_suffixes(self, path: str, expected: DocumentType) -> None:
        assert document_type_from_path(Path(path)) == expected

    def test_unknown_suffix_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot infer"):
            document_type_from_path(Path("foo.xyz"))


class TestEnumSanity:
    def test_mate_type_known_values(self) -> None:
        # Sanity: known enum values should not collide
        assert int(MateType.Coincident) == 0
        assert int(MateType.Gear) == 10

    def test_end_condition_known_values(self) -> None:
        assert int(EndCondition.Blind) == 0
        assert int(EndCondition.MidPlane) == 6

    def test_select_type_known_values(self) -> None:
        assert int(SelectType.Edges) == 1
        assert int(SelectType.Faces) == 2

    def test_save_as_version(self) -> None:
        assert int(SaveAsVersion.CurrentVersion) == 0

    def test_add_mate_error(self) -> None:
        assert int(AddMateError.NoError) == 1
        assert int(AddMateError.IncorrectGearRatios) == 6

    def test_mate_align(self) -> None:
        assert int(MateAlign.Aligned) == 0
        assert int(MateAlign.Closest) == 2
