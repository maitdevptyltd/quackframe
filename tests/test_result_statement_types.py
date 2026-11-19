"""Execute additional result forms completely before rendering their output."""

from pathlib import Path

import duckdb
import pytest

from quackframe import ConfigurationError, ExecutionError, QuackframeConfig
from quackframe.config import LogSetting
from quackframe.sql import (
    execute_sql_file,
    prepare_sql_files,
    validate_external_result_logging,
)

STATEMENTS = [
    "CALL counted_rows()",
    "EXPLAIN ANALYZE INSERT INTO events SELECT * FROM counted_rows()",
    "MERGE INTO events USING counted_rows() AS source ON events.value = source.value "
    "WHEN MATCHED THEN UPDATE SET value = events.value + 30000 "
    "RETURNING value",
]


@pytest.mark.parametrize("statement", STATEMENTS)
@pytest.mark.parametrize("log_setting", ["none", "annotations-only", "all"])
def test_additional_results_execute_once_to_completion(
    tmp_path: Path, statement: str, log_setting: LogSetting
) -> None:
    sql_file = tmp_path / "results.sql"
    annotation = "-- quackframe: log-result\n" if log_setting != "all" else ""
    sql_file.write_text(annotation + statement + ";", encoding="utf-8")
    (prepared,) = prepare_sql_files([sql_file], root=tmp_path, log_setting=log_setting)
    output: list[str] = []

    with duckdb.connect() as connection:
        connection.execute("CREATE SEQUENCE calls START 0 MINVALUE 0")
        connection.execute(
            "CREATE MACRO counted_rows() AS TABLE "
            "SELECT nextval('calls') AS value FROM range(30000)"
        )
        connection.execute("CREATE TABLE events(value BIGINT)")
        if statement.startswith("MERGE"):
            connection.execute("INSERT INTO events SELECT * FROM range(30000)")

        execute_sql_file(connection, prepared, emit_result=output.append)

        assert connection.execute("SELECT currval('calls')").fetchone() == (29999,)
        if statement.startswith("EXPLAIN"):
            assert connection.execute(
                "SELECT count(*), min(value), max(value) FROM events"
            ).fetchone() == (30000, 0, 29999)
        elif statement.startswith("MERGE"):
            assert connection.execute(
                "SELECT count(*), min(value), max(value) FROM events"
            ).fetchone() == (30000, 30000, 59999)

        if log_setting == "none":
            assert output == []
        elif statement.startswith("EXPLAIN"):
            assert len(output) == 1
            assert "explain_key" in output[0]
            assert "explain_value" in output[0]
            assert "analyzed_plan" in output[0]
        else:
            start = 30000 if statement.startswith("MERGE") else 0
            expected = str(
                connection.sql(
                    f"SELECT range AS value FROM range({start}, {start + 30000})"
                )
            )
            assert output == [expected]
            assert "20 shown" in output[0]


@pytest.mark.parametrize("statement", STATEMENTS)
@pytest.mark.parametrize("log_setting", ["annotations-only", "all"])
def test_additional_results_fail_before_emitting_or_running_next_statement(
    tmp_path: Path, statement: str, log_setting: LogSetting
) -> None:
    sql_file = tmp_path / "results.sql"
    annotation = "-- quackframe: log-result\n" if log_setting != "all" else ""
    sql_file.write_text(
        annotation + statement + "; CREATE TABLE should_not_run(value INT);",
        encoding="utf-8",
    )
    (prepared,) = prepare_sql_files([sql_file], root=tmp_path, log_setting=log_setting)
    output: list[str] = []

    with duckdb.connect() as connection:
        connection.execute(
            "CREATE MACRO counted_rows() AS TABLE "
            "SELECT CASE WHEN range = 25000 THEN error('late failure') "
            "ELSE range END AS value FROM range(30000)"
        )
        connection.execute(
            "CREATE TABLE events AS SELECT range AS value FROM range(30000)"
        )
        with pytest.raises(ExecutionError) as captured:
            execute_sql_file(connection, prepared, emit_result=output.append)

        assert captured.value.statement_number == 1
        assert output == []
        assert connection.execute(
            "SELECT table_name FROM duckdb_tables() WHERE NOT internal"
        ).fetchall() == [("events",)]
        assert (
            connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize("statement", STATEMENTS)
@pytest.mark.parametrize("allow_errors", [False, True])
def test_additional_results_require_independent_external_permission(
    tmp_path: Path, statement: str, allow_errors: bool
) -> None:
    sql_file = tmp_path / "results.sql"
    sql_file.write_text("-- quackframe: log-result\n" + statement, encoding="utf-8")
    prepared = prepare_sql_files(
        [sql_file], root=tmp_path, log_setting="annotations-only"
    )
    config = QuackframeConfig(root=tmp_path, allow_external_error_logging=allow_errors)
    with pytest.raises(ConfigurationError, match="External result logging"):
        validate_external_result_logging(
            prepared, config, result_logging_is_external=True
        )

    validate_external_result_logging(
        prepared,
        config.model_copy(update={"allow_external_result_logging": True}),
        result_logging_is_external=True,
    )


def test_merge_without_returning_is_not_selected(tmp_path: Path) -> None:
    sql_file = tmp_path / "merge.sql"
    sql_file.write_text(
        STATEMENTS[2].removesuffix(" RETURNING value"), encoding="utf-8"
    )
    (prepared,) = prepare_sql_files([sql_file], root=tmp_path, log_setting="all")
    assert not prepared.statements[0].emit_result


def test_plain_explain_logs_plan_without_executing_query(tmp_path: Path) -> None:
    sql_file = tmp_path / "explain.sql"
    sql_file.write_text(
        "EXPLAIN INSERT INTO events VALUES (1); -- quackframe: log-result",
        encoding="utf-8",
    )
    (prepared,) = prepare_sql_files(
        [sql_file], root=tmp_path, log_setting="annotations-only"
    )
    output: list[str] = []
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE events(value INT)")
        execute_sql_file(connection, prepared, emit_result=output.append)
        assert connection.execute("SELECT count(*) FROM events").fetchone() == (0,)
    assert len(output) == 1
    assert "physical_plan" in output[0]
