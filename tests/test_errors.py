"""Safe backend diagnostic conversion."""

import duckdb
import pytest

from quackframe.errors import safe_error_reason


@pytest.mark.parametrize(
    "error",
    [
        duckdb.ConversionException("protected-value"),
        duckdb.ParserException("protected-value"),
        duckdb.CatalogException("protected-value"),
        ValueError("protected-value"),
        RuntimeError("protected-value\nsecond line"),
    ],
)
def test_external_error_text_is_never_forwarded(error: Exception) -> None:
    assert "protected-value" not in safe_error_reason(error)


def test_unknown_error_does_not_need_to_render_its_message() -> None:
    class UnprintableError(Exception):
        def __str__(self) -> str:
            raise AssertionError("External exception text must not be inspected")

    assert safe_error_reason(UnprintableError()) == "The operation failed"
