"""Unit tests for solidworks_com.drawing_doc (no SOLIDWORKS required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from solidworks_com.drawing_doc import DrawingDoc
from solidworks_com.errors import SolidWorksError


def _make_drawing_doc() -> DrawingDoc:
    """Return a DrawingDoc with a mocked COM object."""
    com = MagicMock()
    doc = DrawingDoc.__new__(DrawingDoc)
    doc.com = com
    return doc


class TestDrawingDocAddDimension:
    def test_raises_not_implemented(self) -> None:
        doc = _make_drawing_doc()
        with pytest.raises(NotImplementedError, match="not implemented"):
            doc.add_dimension("edge1", "edge2", 10.0)

    def test_raises_regardless_of_dim_type(self) -> None:
        doc = _make_drawing_doc()
        with pytest.raises(NotImplementedError):
            doc.add_dimension("a", "b", 5.0, dim_type="radial")


class TestDrawingDocInsertModelView:
    def test_returns_view_on_success(self) -> None:
        doc = _make_drawing_doc()
        fake_view = MagicMock()
        doc.com.CreateDrawView.return_value = fake_view
        result = doc.insert_model_view("part.sldprt")
        assert result is fake_view

    def test_falls_back_to_insert_model(self) -> None:
        doc = _make_drawing_doc()
        doc.com.CreateDrawView.return_value = None   # primary API returns None
        fake_view = MagicMock()
        doc.com.InsertModelInPrefPosition.return_value = fake_view
        result = doc.insert_model_view("part.sldprt")
        assert result is fake_view

    def test_raises_when_both_apis_fail(self) -> None:
        doc = _make_drawing_doc()
        doc.com.CreateDrawView.return_value = None
        doc.com.InsertModelInPrefPosition.return_value = None
        with pytest.raises(SolidWorksError, match="Failed to insert model view"):
            doc.insert_model_view("part.sldprt")


class TestDrawingDocAddSheet:
    def test_returns_sheet(self) -> None:
        doc = _make_drawing_doc()
        fake_sheet = MagicMock()
        doc.com.NewSheet3.return_value = fake_sheet
        result = doc.add_sheet("MySheet")
        assert result is fake_sheet

    def test_returns_none_when_api_missing(self) -> None:
        doc = _make_drawing_doc()
        doc.com.NewSheet3.side_effect = AttributeError("no such method")
        result = doc.add_sheet("MySheet")
        assert result is None
