"""Unit tests for SolidWorks class lifecycle (shutdown, __repr__, context manager).

These tests do not require a running SOLIDWORKS instance. They exercise the
state management of the SolidWorks wrapper using a MagicMock com object.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from solidworks_com.app import SolidWorks


def _make_solidworks(revision: str = "33.0") -> SolidWorks:
    """Build a SolidWorks wrapper with a mocked com object."""
    com = MagicMock()
    com.RevisionNumber = revision
    return SolidWorks(com)


class TestRepr:
    def test_repr_includes_revision_and_state(self) -> None:
        sw = _make_solidworks(revision="33.5.0")
        text = repr(sw)
        assert "SolidWorks" in text
        assert "33.5.0" in text
        assert "open" in text

    def test_repr_after_shutdown_shows_closed(self) -> None:
        sw = _make_solidworks()
        sw.shutdown()
        assert "closed" in repr(sw)

    def test_repr_falls_back_on_com_error(self) -> None:
        # A com object whose attribute access raises
        com = MagicMock()
        type(com).RevisionNumber = property(  # type: ignore[assignment]
            lambda self: (_ for _ in ()).throw(Exception("boom"))
        )
        sw = SolidWorks(com)
        text = repr(sw)
        assert text.startswith("SolidWorks(")


class TestShutdown:
    def test_does_not_call_coinitialize_when_not_owner(self) -> None:
        sw = _make_solidworks()
        # Manually constructed (not via connect), so _owns_apartment is False
        assert sw._owns_apartment is False
        # Patch the import path to verify CoUninitialize is never reached
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pc = MagicMock()
            mock_pw32.return_value = (mock_pc, MagicMock())
            sw.shutdown(exit_app=False)
            mock_pc.CoUninitialize.assert_not_called()

    def test_calls_exit_app_by_default(self) -> None:
        sw = _make_solidworks()
        sw._owns_apartment = True  # pretend we connected
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pw32.return_value = (MagicMock(), MagicMock())
            sw.shutdown()
        sw.com.ExitApp.assert_called_once()

    def test_skip_exit_app(self) -> None:
        sw = _make_solidworks()
        sw._owns_apartment = True
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pw32.return_value = (MagicMock(), MagicMock())
            sw.shutdown(exit_app=False)
        sw.com.ExitApp.assert_not_called()

    def test_idempotent(self) -> None:
        sw = _make_solidworks()
        sw._owns_apartment = True
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pw32.return_value = (MagicMock(), MagicMock())
            sw.shutdown()
            sw.shutdown()  # second call should not blow up
        # ExitApp should only have been called once
        sw.com.ExitApp.assert_called_once()

    def test_exit_app_failure_does_not_propagate(self) -> None:
        sw = _make_solidworks()
        sw._owns_apartment = True
        sw.com.ExitApp.side_effect = Exception("kaboom")
        # Should swallow the error and still uninit
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pc = MagicMock()
            mock_pw32.return_value = (mock_pc, MagicMock())
            sw.shutdown()
        # CoUninitialize should still have been called
        mock_pc.CoUninitialize.assert_called_once()
        # And the apartment flag should be cleared
        assert sw._owns_apartment is False


class TestContextManager:
    def test_with_block_returns_self(self) -> None:
        sw = _make_solidworks()
        with sw as inner:
            assert inner is sw

    def test_with_block_calls_shutdown(self) -> None:
        sw = _make_solidworks()
        sw._owns_apartment = True
        with patch("solidworks_com.app.import_pywin32") as mock_pw32:
            mock_pw32.return_value = (MagicMock(), MagicMock())
            with sw:
                pass
        sw.com.ExitApp.assert_called_once()
        assert sw._owns_apartment is False
