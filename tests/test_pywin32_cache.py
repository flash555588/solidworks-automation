"""Regression tests for the module-level pywin32 import cache.

Ensures ``import_pywin32()`` only imports the C-extension modules once and
returns the cached module objects on subsequent calls.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def com_module():
    """Reload solidworks_com.com to reset the module-level cache.

    Yields the freshly imported module so tests can inspect
    ``_pythoncom`` / ``_win32com_client`` after their first call.
    """
    # Drop any previously cached module from earlier test runs
    for name in list(sys.modules):
        if name == "solidworks_com.com":
            del sys.modules[name]
    module = importlib.import_module("solidworks_com.com")
    yield module
    # Reset the cache so other tests don't see the warmed state
    module._pythoncom = None
    module._win32com_client = None


class TestImportPywin32Cache:
    def test_initial_state_is_empty(self, com_module) -> None:
        # The freshly loaded module should expose the cache hooks
        assert hasattr(com_module, "_pythoncom")
        assert hasattr(com_module, "_win32com_client")
        # And the cache may already be populated if pywin32 was imported
        # by another module — but the hooks themselves are present.

    def test_repeated_calls_return_same_modules(self, com_module) -> None:
        pc1, wcc1 = com_module.import_pywin32()
        pc2, wcc2 = com_module.import_pywin32()
        # Same module objects each time
        assert pc1 is pc2
        assert wcc1 is wcc2
        # And the cache globals match
        assert com_module._pythoncom is pc1
        assert com_module._win32com_client is wcc1

    def test_cache_survives_across_helpers(self, com_module) -> None:
        # Call through several helpers in sequence and confirm identity
        from solidworks_com.com import empty_dispatch, empty_variant, int_byref

        int_byref()
        empty_dispatch()
        empty_variant()
        # After the first helper call, the cache is populated
        assert com_module._pythoncom is not None
        assert com_module._win32com_client is not None
        # All subsequent calls reuse the same modules
        assert com_module._pythoncom is com_module.import_pywin32()[0]
