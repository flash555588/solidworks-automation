"""Unit tests for solidworks_com.errors."""

from __future__ import annotations

import pytest

from solidworks_com.errors import SolidWorksError


class TestSolidWorksError:
    def test_basic_message(self) -> None:
        err = SolidWorksError("boom")
        assert str(err) == "boom"
        assert err.errors == 0
        assert err.warnings == 0
        assert err.method is None
        assert err.args_payload is None
        assert err.com_error is None

    def test_with_errors_and_warnings(self) -> None:
        err = SolidWorksError("oops", errors=2, warnings=1)
        text = str(err)
        assert "oops" in text
        assert "errors=2" in text
        assert "warnings=1" in text

    def test_method_in_message(self) -> None:
        err = SolidWorksError("save failed", method="IModelDoc2.Save3")
        assert "method=IModelDoc2.Save3" in str(err)

    def test_args_in_message(self) -> None:
        err = SolidWorksError("bad call", method="Foo.Bar", args=("a", 1, 2.5))
        text = str(err)
        assert "args=('a', 1, 2.5)" in text
        assert err.args_payload == ("a", 1, 2.5)

    def test_args_normalized_to_tuple(self) -> None:
        err = SolidWorksError("x", args=["a", "b"])
        assert err.args_payload == ("a", "b")

    def test_com_error_in_message(self) -> None:
        com_err = OSError("RPC server unavailable")
        err = SolidWorksError("dispatch failed", com_error=com_err)
        text = str(err)
        assert "com_error=OSError" in text
        assert "RPC server unavailable" in text
        assert err.com_error is com_err

    def test_long_args_truncated(self) -> None:
        big = "x" * 500
        err = SolidWorksError("x", args=(big,))
        text = str(err)
        # The arg should be truncated to fit in a single line
        assert "..." in text
        # And the full untruncated value should be accessible
        assert err.args_payload == (big,)

    def test_subclass_of_runtime_error(self) -> None:
        err = SolidWorksError("x")
        assert isinstance(err, RuntimeError)
        with pytest.raises(RuntimeError):
            raise err

    def test_all_fields_together(self) -> None:
        com_err = ValueError("inner")
        err = SolidWorksError(
            "complex failure",
            errors=3,
            warnings=1,
            method="IModelDoc2.SaveAs3",
            args=("out.SLDPRT", 0, 1, None, None, 0, 0),
            com_error=com_err,
        )
        text = str(err)
        assert "errors=3" in text
        assert "warnings=1" in text
        assert "method=IModelDoc2.SaveAs3" in text
        assert "args=(" in text
        assert "com_error=ValueError" in text
