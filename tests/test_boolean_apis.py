"""Smoke tests for the boolean / face-based APIs.

These tests verify the API surface is present on ``ModelDoc`` and that
``_face_centroid`` / ``_body_centroid`` helpers behave correctly with
a magic-mocked COM object. They do *not* call SOLIDWORKS — running
real extrude/boolean operations requires a live SW instance and is
covered by the manual examples in ``examples/``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from solidworks_com.errors import SolidWorksError
from solidworks_com.model import ModelDoc, _as_list, _body_centroid, _face_centroid


def _make_doc() -> ModelDoc:
    """Build a ModelDoc with a mocked COM object."""
    com = MagicMock()
    return ModelDoc(com)


class TestNewAPIPresent:
    """The new boolean / face-based APIs must exist on ModelDoc."""

    def test_find_face_at_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "find_face_at")
        assert callable(doc.find_face_at)

    def test_extrude_cylinder_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "extrude_cylinder")
        assert callable(doc.extrude_cylinder)

    def test_bool_subtract_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "bool_subtract")
        assert callable(doc.bool_subtract)

    def test_make_hole_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "make_hole")
        assert callable(doc.make_hole)

    def test_bodies_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "bodies")
        assert callable(doc.bodies)

    def test_active_body_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "active_body")
        assert callable(doc.active_body)

    def test_sketch_on_face_at_exists(self) -> None:
        doc = _make_doc()
        assert hasattr(doc, "sketch_on_face_at")
        assert callable(doc.sketch_on_face_at)


class TestBodiesHelper:
    def test_bodies_returns_empty_when_com_errors(self) -> None:
        com = MagicMock()
        com.GetBodies.side_effect = Exception("no part")
        doc = ModelDoc(com)
        assert doc.bodies() == []

    def test_bodies_returns_list_from_com(self) -> None:
        com = MagicMock()
        body1, body2 = MagicMock(), MagicMock()
        com.GetBodies.return_value = (body1, body2)
        doc = ModelDoc(com)
        bodies = doc.bodies()
        assert len(bodies) == 2
        assert bodies[0] is body1
        assert bodies[1] is body2

    def test_bodies_normalises_via_as_list(self) -> None:
        com = MagicMock()
        body1 = MagicMock()
        com.GetBodies.return_value = [body1]  # plain list
        doc = ModelDoc(com)
        bodies = doc.bodies()
        assert len(bodies) == 1
        assert bodies[0] is body1

    def test_active_body_returns_last_body(self) -> None:
        com = MagicMock()
        b1, b2 = MagicMock(), MagicMock()
        com.GetBodies.return_value = (b1, b2)
        doc = ModelDoc(com)
        assert doc.active_body() is b2

    def test_active_body_returns_none_when_no_bodies(self) -> None:
        com = MagicMock()
        com.GetBodies.return_value = ()
        doc = ModelDoc(com)
        assert doc.active_body() is None


class TestFindFaceAt:
    def test_raises_on_no_face(self) -> None:
        com = MagicMock()
        com.Extension.SelectByID2.return_value = False
        doc = ModelDoc(com)
        with pytest.raises(SolidWorksError, match="Failed to find a body FACE"):
            doc.find_face_at(0.0, 0.0, 0.0)

    def test_returns_face_when_found(self) -> None:
        com = MagicMock()
        com.Extension.SelectByID2.return_value = True
        face = MagicMock()
        # selected_object -> GetSelectedObject6
        com.SelectionManager.GetSelectedObject6.return_value = face
        doc = ModelDoc(com)
        result = doc.find_face_at(1.0, 2.0, 3.0)
        assert result is face
        # Verify the call was made with FACE type
        com.Extension.SelectByID2.assert_called_once()
        call_args = com.Extension.SelectByID2.call_args[0]
        assert call_args[0] == ""  # name
        assert call_args[1] == "FACE"  # type

    def test_returns_none_when_not_required(self) -> None:
        com = MagicMock()
        com.Extension.SelectByID2.return_value = False
        doc = ModelDoc(com)
        assert doc.find_face_at(0, 0, 0, require=False) is None


class TestFaceCentroidHelper:
    def test_returns_zero_when_getbox_errors(self) -> None:
        face = MagicMock()
        face.GetBox.side_effect = Exception("boom")
        assert _face_centroid(face) == (0.0, 0.0, 0.0)

    def test_returns_centroid_of_bbox(self) -> None:
        face = MagicMock()
        # GetBox returns 6 values: xMin, yMin, zMin, xMax, yMax, zMax
        face.GetBox.return_value = (-1.0, -2.0, -3.0, 3.0, 4.0, 5.0)
        assert _face_centroid(face) == (1.0, 1.0, 1.0)

    def test_handles_six_value_list(self) -> None:
        face = MagicMock()
        face.GetBox.return_value = [0.0, 0.0, 0.0, 10.0, 20.0, 30.0]
        assert _face_centroid(face) == (5.0, 10.0, 15.0)


class TestBodyCentroidHelper:
    def test_returns_centroid(self) -> None:
        body = MagicMock()
        body.GetBodyBox.return_value = (0.0, 0.0, 0.0, 100.0, 50.0, 25.0)
        assert _body_centroid(body) == (50.0, 25.0, 12.5)

    def test_zero_on_error(self) -> None:
        body = MagicMock()
        body.GetBodyBox.side_effect = Exception("boom")
        assert _body_centroid(body) == (0.0, 0.0, 0.0)


class TestAsListReuse:
    """``_as_list`` is the helper used by ``bodies()``; make sure it
    still handles None, plain list, and tuple the same way as before."""
    def test_none(self) -> None:
        assert _as_list(None) == []

    def test_list_passthrough(self) -> None:
        items = [1, 2, 3]
        assert _as_list(items) == items

    def test_tuple_to_list(self) -> None:
        assert _as_list((1, 2, 3)) == [1, 2, 3]

    def test_string_kept_whole(self) -> None:
        # Strings should not be split into characters; COM sometimes
        # returns strings where a list was expected.
        assert _as_list("hello") == ["hello"]
