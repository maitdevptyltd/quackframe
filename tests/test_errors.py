"""Safe backend diagnostic conversion."""

import json
import traceback
from pathlib import Path
from typing import Literal

import duckdb
import pytest

from quackframe import QuackframeConfig
from quackframe.engine import execute_plan
from quackframe.errors import safe_error_reason
from quackframe.models import ExecutionResult
from quackframe.sql import prepare_sql_files


def _run_safe(sql_files: list[Path], *, config: QuackframeConfig) -> ExecutionResult:
    """Exercise safe diagnostic construction independently of runtime routing."""

    prepared = prepare_sql_files(
        sql_files,
        root=config.root,
        log_setting=config.log_setting,
        include_error_details=False,
    )
    return execute_plan(prepared, config)


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


OBSERVATIONS = Path(__file__).parent / "investigations/duckdb_errors/observations.json"


@pytest.mark.parametrize(
    ("scenario", "expected", "omitted"),
    [
        ("binder_literal", "absent", "FAKE_LITERAL_SECRET"),
        ("catalog_literal", "absent", "FAKE_LITERAL_SECRET"),
        ("conversion_row", "INT32", "FAKE_ROW_PERSONAL"),
        ("constraint_row", "column 'v'", "FAKE_ROW_BUSINESS"),
        ("csv_row", "input line 2", "FAKE_ROW_PERSONAL"),
        ("json_row", "Malformed JSON", "FAKE_ROW_PERSONAL"),
        ("url_blocked", "fake_host_private.invalid/file", "FAKE_URL_TOKEN"),
        ("pivot_candidate", "missing", "FAKE_ROW_BUSINESS"),
        ("parser_literal", "SQL syntax", "FAKE_LITERAL_SECRET"),
        ("custom_row", "InvalidInputException", "FAKE_ROW_PERSONAL"),
        ("udf_message", "InvalidInputException", "FAKE_UPSTREAM_SECRET"),
        ("missing_file", "FAKE_PATH_PRIVATE/missing.csv", "No secret marker"),
    ],
)
def test_recorded_diagnostics_preserve_context_without_values(
    scenario: str, expected: str, omitted: str
) -> None:
    records = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    record = next(
        item
        for item in records
        if item["json_mode"] and item["scenario"]["id"] == scenario
    )
    error = getattr(duckdb, record["exception"]["class"])(
        record["exception"]["message"]
    )
    reason = safe_error_reason(error)
    assert expected in reason
    assert omitted not in reason
    assert "Original Line:" not in reason


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        '{"position": 2}',
        '{"exception_type": "Conversion", '
        '"exception_message": "new format private-data"}',
    ],
)
def test_unsupported_structured_errors_fall_back(text: str) -> None:
    reason = safe_error_reason(duckdb.ConversionException(text))
    assert "ConversionException" in reason
    assert "private-data" not in reason


@pytest.mark.parametrize(
    "sql, statement, line, column, fragment",
    [
        ("SELECT 1;\nSELECT absent", 2, 2, 8, "absent"),
        ("SELECT 'é';\nSELECT '日', absent", 2, 2, 13, "absent"),
        ("SELECT 1;\nSELECT 'private-data' + FROM x", 2, 2, 25, "SQL syntax"),
        (
            "PIVOT (SELECT 'private-data' k, 1 v) ON k USING sum(v);\nSELECT missing",
            2,
            2,
            8,
            "missing",
        ),
        ("SELECT CAST('private-data' AS INTEGER)", 1, 1, 8, "INT32"),
    ],
)
@pytest.mark.parametrize("log_setting", ["none", "all"])
def test_execution_diagnostics_and_original_locations(
    tmp_path: Path,
    sql: str,
    statement: int,
    line: int,
    column: int,
    fragment: str,
    log_setting: Literal["none", "all"],
) -> None:
    from quackframe import ExecutionError, QuackframeConfig

    path = tmp_path / "diagnostics.sql"
    path.write_text(sql, encoding="utf-8")
    with pytest.raises(ExecutionError) as captured:
        _run_safe(
            [path], config=QuackframeConfig(root=tmp_path, log_setting=log_setting)
        )
    error = captured.value
    assert error.statement_number == statement
    if log_setting == "all" and fragment in {"absent", "missing"}:
        # Relation binding omits its position; do not invent a source location.
        assert (error.line, error.column) == (None, None)
    else:
        assert (error.line, error.column) == (line, column)
    assert fragment in str(error)
    assert "private-data" not in "".join(traceback.format_exception(error))


def test_pivot_counts_source_statements_and_runs_once(tmp_path: Path) -> None:
    from quackframe import QuackframeConfig

    path = tmp_path / "pivot.sql"
    path.write_text(
        "CREATE TABLE t AS PIVOT (SELECT 'a' k, 1 v) ON k USING sum(v); "
        "SELECT * FROM t;",
        encoding="utf-8",
    )
    result = _run_safe(
        [path], config=QuackframeConfig(root=tmp_path, log_setting="none")
    )
    assert result.statement_count == 2


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("constraint_row", "unique constraint"),
        ("json_row", "Malformed JSON"),
        ("pivot_candidate", "missing"),
        ("conversion_row", "INT32"),
    ],
)
def test_observed_row_failures_through_execution(
    tmp_path: Path, scenario: str, expected: str
) -> None:
    from quackframe import ExecutionError, QuackframeConfig

    records = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    case = next(
        item["scenario"] for item in records if item["scenario"]["id"] == scenario
    )
    sql = ";\n".join([*case["setup"], case["sql"]])
    path = tmp_path / "rows.sql"
    path.write_text(sql, encoding="utf-8")
    with pytest.raises(ExecutionError) as captured:
        _run_safe([path], config=QuackframeConfig(root=tmp_path, log_setting="none"))
    assert expected in str(captured.value)
    assert "FAKE_ROW_" not in "".join(traceback.format_exception(captured.value))


def test_csv_failure_retains_file_line_column_and_expected_type(tmp_path: Path) -> None:
    from quackframe import ExecutionError, QuackframeConfig

    csv = tmp_path / "records.csv"
    csv.write_text("v\nprivate-data\n", encoding="utf-8")
    path = tmp_path / "import.sql"
    path.write_text(
        f"SELECT * FROM read_csv('{csv.as_posix()}', "
        "columns={'v': 'INTEGER'}, header=true)",
        encoding="utf-8",
    )
    with pytest.raises(ExecutionError) as captured:
        _run_safe([path], config=QuackframeConfig(root=tmp_path, log_setting="none"))
    message = str(captured.value)
    for expected in ("records.csv", "input line 2", "column 'v'", "expected INTEGER"):
        assert expected in message
    assert "private-data" not in "".join(traceback.format_exception(captured.value))


@pytest.mark.parametrize("expression", ["json(v)", "json_extract(v, '$.key')"])
def test_json_functions_omit_stored_values_but_keep_input_position(
    tmp_path: Path, expression: str
) -> None:
    from quackframe import ExecutionError, QuackframeConfig

    path = tmp_path / "json.sql"
    path.write_text(
        "CREATE TABLE payloads AS SELECT 'private-row-data' v; "
        f"SELECT {expression} FROM payloads;",
        encoding="utf-8",
    )
    with pytest.raises(ExecutionError) as captured:
        _run_safe([path], config=QuackframeConfig(root=tmp_path, log_setting="none"))
    assert "Invalid Input: Malformed JSON at input byte 0" in str(captured.value)
    assert "private-row-data" not in "".join(traceback.format_exception(captured.value))


def test_locked_configuration_supports_multiple_files_and_diagnostics(
    tmp_path: Path,
) -> None:
    from quackframe import DuckDBConfig, ExecutionError, QuackframeConfig

    first = tmp_path / "first.sql"
    first.write_text("SELECT 1;", encoding="utf-8")
    second = tmp_path / "second.sql"
    second.write_text("SELECT 2;", encoding="utf-8")
    config = QuackframeConfig(
        root=tmp_path,
        log_setting="none",
        duckdb=DuckDBConfig(settings={"lock_configuration": "true"}),
    )
    assert _run_safe([first, second], config=config).statement_count == 2

    second.write_text("SELECT absent;", encoding="utf-8")
    with pytest.raises(ExecutionError) as captured:
        _run_safe([first, second], config=config)
    assert "Column 'absent' was not found" in str(captured.value)
    assert (captured.value.line, captured.value.column) == (1, 8)
