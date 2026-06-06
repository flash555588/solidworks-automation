"""Unit tests for scripts/build_sw_api_docs.py.

These tests cover ``resolve_docset_paths`` (a small pure-function that joins
``api_dir`` with each docset's relative path) without invoking the heavy
``markdownify`` / ``bs4`` imports. We load the module via importlib with a
shim so the test runs even when those dev dependencies are absent.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_build_module() -> types.ModuleType:
    """Load scripts/build_sw_api_docs.py with markdownify stubbed out."""
    if "build_sw_api_docs" in sys.modules:
        return sys.modules["build_sw_api_docs"]

    # Stub the optional dev dependencies the module imports at the top
    if "markdownify" not in sys.modules:
        md_stub = types.ModuleType("markdownify")

        def _markdownify(value: object, **_: object) -> str:  # pragma: no cover - never used here
            return str(value)

        md_stub.markdownify = _markdownify
        sys.modules["markdownify"] = md_stub

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_sw_api_docs.py"
    spec = importlib.util.spec_from_file_location("build_sw_api_docs", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_sw_api_docs"] = module
    spec.loader.exec_module(module)
    return module


class TestResolveDocsetPaths:
    def test_returns_full_dict(self) -> None:
        module = _load_build_module()
        api = Path("C:/api")
        resolved = module.resolve_docset_paths(api)
        assert set(resolved) == set(module.DOCSETS)

    def test_paths_are_joined_to_api_dir(self) -> None:
        module = _load_build_module()
        api = Path("C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api")
        resolved = module.resolve_docset_paths(api)
        # sldworksapi's cab is three path segments deep
        cab = resolved["sldworksapi"]["cab"]
        assert cab == api / "HelpViewer" / "sldworksapi" / "apihelpviewer.cab"
        # swconst is parallel to sldworksapi
        const = resolved["swconst"]["cab"]
        assert const == api / "HelpViewer" / "swconst" / "apienumshelpviewer.cab"
        # chm files sit directly under api_dir
        assert resolved["swdocmgrapi"]["chm"] == api / "swdocmgrapi.chm"

    def test_each_docset_has_either_cab_or_chm(self) -> None:
        module = _load_build_module()
        resolved = module.resolve_docset_paths(Path("X:/api"))
        for name, config in resolved.items():
            has_source = ("cab" in config) or ("chm" in config)
            assert has_source, f"docset {name!r} has no source path"

    def test_resolution_uses_posix_conventions(self) -> None:
        module = _load_build_module()
        api = Path("/opt/sw/api")
        resolved = module.resolve_docset_paths(api)
        assert str(resolved["swcommands"]["chm"]).endswith("swcommands.chm")

    def test_default_api_dir_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOLIDWORKS_API_DIR", "D:/env/api")
        # Re-import the module so DEFAULT_API_DIR picks up the env var
        for name in list(sys.modules):
            if name == "build_sw_api_docs":
                del sys.modules[name]
        module = _load_build_module()
        assert Path("D:/env/api") == module.DEFAULT_API_DIR
