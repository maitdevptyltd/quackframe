"""Ordered SQL execution and database lifecycle tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

import quackframe.engine as engine_module
import quackframe.sql as sql_module
from quackframe import (
    ConfigurationError,
    DatabaseConfig,
    ExecutionError,
    QuackframeConfig,
    run,
)
from quackframe.config import LogSetting
from quackframe.engine import execute_plan
from quackframe.runtimes import registry as runtime_registry
from quackframe.runtimes.registry import RuntimeRegistration
from quackframe.sql import execute_sql_file, prepare_sql_files


def _write(path: Path, sql: str) -> Path:
    path.write_text(sql, encoding="utf-8")
    return path


def test_ordered_files_share_one_session(tmp_path: Path) -> None:
    create = _write(
        tmp_path / "01-create.sql",
        "CREATE TEMP TABLE shared_state(value INTEGER);",
    )
    use = _write(
        tmp_path / "02-use.sql",
        "INSERT INTO shared_state VALUES (1); SELECT count(*) FROM shared_state;",
    )

    result = run([create, use], config=QuackframeConfig(root=tmp_path))

    assert tuple(file.path.name for file in result.files) == (
        "01-create.sql",
        "02-use.sql",
    )
    assert result.statement_count == 3


@pytest.mark.parametrize("wall_clock_seconds", [-3600, 3600])
def test_elapsed_uses_monotonic_time_despite_wall_clock_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wall_clock_seconds: int
) -> None:
    sql_file = _write(tmp_path / "duration.sql", "SELECT 1; SELECT 2;")
    config = QuackframeConfig(root=tmp_path, log_setting="none")
    prepared = prepare_sql_files([sql_file], root=tmp_path, log_setting="none")
    start = datetime(2026, 10, 14, tzinfo=UTC)
    end = start + timedelta(seconds=wall_clock_seconds)

    # Keep a jumping wall clock available to catch a return to datetime timing.
    for module in (engine_module, sql_module):
        monkeypatch.setattr(
            module, "datetime", Mock(now=Mock(side_effect=[start, end])), raising=False
        )
    monkeypatch.setattr(engine_module, "perf_counter", Mock(side_effect=[10.0, 15.5]))
    monkeypatch.setattr(
        sql_module,
        "perf_counter",
        Mock(side_effect=[11.0, 11.1, 11.5, 11.6, 12.0, 12.25]),
    )

    result = execute_plan(prepared, config)

    assert result.elapsed == timedelta(seconds=5.5)
    assert result.files[0].elapsed == timedelta(seconds=1.25)
    assert result.files[0].path == sql_file
    assert result.statement_count == result.files[0].statement_count == 2
    assert result.runtime == "direct"
    assert result.database_mode == "memory"


def test_execution_stops_at_first_failing_statement(tmp_path: Path) -> None:
    database_path = tmp_path / "execution.duckdb"
    first = _write(tmp_path / "01.sql", "CREATE TABLE events(value INTEGER);")
    failing = _write(
        tmp_path / "02.sql",
        "INSERT INTO events VALUES (1); SELECT * FROM table_that_does_not_exist;",
    )
    later = _write(tmp_path / "03.sql", "INSERT INTO events VALUES (2);")
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="persistent", path=database_path),
    )

    with pytest.raises(ExecutionError) as captured:
        run([first, failing, later], config=config)

    assert captured.value.sql_file == failing
    assert captured.value.statement_number == 2
    assert "SELECT *" not in str(captured.value)
    with duckdb.connect(str(database_path)) as connection:
        assert connection.execute("SELECT value FROM events").fetchall() == [(1,)]


def test_temporary_database_is_removed_after_success(tmp_path: Path) -> None:
    sql_file = _write(tmp_path / "run.sql", "CREATE TABLE example(value INTEGER);")
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="temporary"),
    )

    run([sql_file], config=config)

    assert not list((tmp_path / ".quackframe" / "tmp").iterdir())


def test_empty_input_fails_before_database_creation(tmp_path: Path) -> None:
    database_path = tmp_path / "not-created.duckdb"
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="persistent", path=database_path),
    )

    with pytest.raises(ConfigurationError, match="At least one SQL file"):
        run([], config=config)

    assert not database_path.exists()


def test_annotations_only_emits_only_annotated_results(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        """
SELECT 'hidden' AS value;
-- quackframe: log-result
SELECT 'shown' AS value;
""".strip(),
    )

    run([sql_file], config=QuackframeConfig(root=tmp_path))

    output = capsys.readouterr().out
    assert "shown" in output
    assert "hidden" not in output


def test_none_ignores_annotations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        "-- quackframe: log-result\nSELECT 'hidden' AS value;",
    )

    run(
        [sql_file],
        config=QuackframeConfig(root=tmp_path, log_setting="none"),
    )

    assert capsys.readouterr().out == ""


def test_all_emits_annotated_and_unannotated_results_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        """
-- quackframe: log-result
SELECT 'first-value' AS value;
SELECT 'second-value' AS value;
""".strip(),
    )

    run(
        [sql_file],
        config=QuackframeConfig(root=tmp_path, log_setting="all"),
    )

    output = capsys.readouterr().out
    assert output.count("first-value") == 1
    assert output.count("second-value") == 1


def test_annotation_binding_ignores_strings_and_semicolons(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        """
SELECT '-- quackframe: log-result; returning' AS hidden;
-- ordinary comment
-- quackframe: log-result
SELECT 'shown;value' AS visible;
""".strip(),
    )

    run([sql_file], config=QuackframeConfig(root=tmp_path))

    output = capsys.readouterr().out
    assert "shown;value" in output
    assert "returning" not in output


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    "comment", ["", "/* ordinary comment */ ", "/* outer /* inner */ comment */ "]
)
@pytest.mark.parametrize("log_setting", ["annotations-only", "none", "all"])
def test_trailing_annotation_never_selects_next_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    newline: str,
    comment: str,
    log_setting: LogSetting,
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        "SELECT 'shown-é' AS value; "
        + comment
        + "-- quackframe: log-result"
        + newline
        + "SELECT 'private-next' AS value;",
    )

    run([sql_file], config=QuackframeConfig(root=tmp_path, log_setting=log_setting))

    output = capsys.readouterr().out
    assert output.count("shown-é") == (0 if log_setting == "none" else 1)
    assert output.count("private-next") == (1 if log_setting == "all" else 0)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'shown' -- quackframe: log-result",
        "SELECT 'shown'; -- quackframe: log-result",
        "SELECT 'shown' /* ordinary comment */ -- quackframe: log-result",
        "SELECT 'shown' -- quackframe: log-result\n-- ordinary final comment",
        "SELECT 'shown' AS \"quoted -- name\" -- quackframe: log-result",
        "SELECT $$shown$$ -- quackframe: log-result",
        "SELECT $tag$shown$tag$ -- quackframe: log-result",
        "SELECT 'it''s shown' -- quackframe: log-result",
    ],
)
def test_final_trailing_annotation_emits_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sql: str
) -> None:
    sql_file = _write(tmp_path / "results.sql", sql)

    run([sql_file], config=QuackframeConfig(root=tmp_path))

    assert "shown" in capsys.readouterr().out


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT '-- quackframe: log-result'",
        "SELECT $$-- quackframe: log-result$$",
        'SELECT 1 AS "-- quackframe: log-result"',
        "SELECT 1 /* -- quackframe: log-result */",
        "SELECT 1/* -- quackframe: log-result */",
        "SELECT 1/* -- quackframe: log-result\n*/",
        "SELECT -- quackframe: log-result\n1;",
        "SELECT 1; -- ordinary comment\nSELECT 'private-next';",
    ],
)
def test_annotation_text_inside_sql_does_not_select_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sql: str
) -> None:
    sql_file = _write(tmp_path / "results.sql", sql)

    run([sql_file], config=QuackframeConfig(root=tmp_path))

    assert capsys.readouterr().out == ""


def test_trailing_annotation_rejects_non_result_statement(tmp_path: Path) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        "CREATE TABLE example(value INTEGER); -- quackframe: log-result\nSELECT 1;",
    )

    with pytest.raises(ExecutionError, match="requires a result-producing statement"):
        prepare_sql_files([sql_file], root=tmp_path, log_setting="annotations-only")


def test_native_relation_rendering_owns_truncation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        "-- quackframe: log-result\nSELECT i FROM range(25) AS rows(i);",
    )

    run([sql_file], config=QuackframeConfig(root=tmp_path))

    output = capsys.readouterr().out
    assert "25 rows" in output
    assert "20 shown" in output


@pytest.mark.parametrize("log_setting", ["none", "annotations-only", "all"])
def test_result_logging_detects_errors_beyond_preview(
    tmp_path: Path, log_setting: LogSetting
) -> None:
    annotation = "-- quackframe: log-result\n" if log_setting != "all" else ""
    sql_file = _write(
        tmp_path / "late-error.sql",
        annotation + "SELECT CASE WHEN i = 25000 THEN error('late failure') ELSE i END "
        "FROM range(1, 30001) AS rows(i); CREATE TEMP TABLE should_not_run(i INT);",
    )
    (prepared,) = prepare_sql_files([sql_file], root=tmp_path, log_setting=log_setting)
    output: list[str] = []

    with duckdb.connect() as connection:
        with pytest.raises(ExecutionError) as captured:
            execute_sql_file(connection, prepared, emit_result=output.append)

        assert captured.value.sql_file == sql_file
        assert captured.value.statement_number == 1
        assert output == []
        assert (
            connection.execute(
                "SELECT table_name FROM duckdb_tables() WHERE NOT internal"
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize("log_setting", ["none", "annotations-only", "all"])
def test_result_logging_executes_every_row_exactly_once(
    tmp_path: Path, log_setting: LogSetting
) -> None:
    calls = [0] * 30000

    def counted(value: int) -> int:
        calls[value] += 1
        return value

    annotation = "-- quackframe: log-result\n" if log_setting != "all" else ""
    sql_file = _write(
        tmp_path / "counted.sql",
        annotation + "SELECT counted(i) AS value FROM range(30000) AS rows(i);",
    )
    (prepared,) = prepare_sql_files([sql_file], root=tmp_path, log_setting=log_setting)
    output: list[str] = []

    with duckdb.connect() as connection:
        connection.create_function(  # pyright: ignore[reportUnknownMemberType]
            "counted", counted, side_effects=True
        )
        execute_sql_file(connection, prepared, emit_result=output.append)

        assert calls == [1] * 30000
        expected = str(connection.sql("SELECT i AS value FROM range(30000) AS rows(i)"))
        assert output == ([] if log_setting == "none" else [expected])
        assert (
            connection.execute(
                "SELECT table_name FROM duckdb_tables() WHERE NOT internal"
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
            == []
        )


def test_annotated_returning_after_unicode_emits_and_executes_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "results.duckdb"
    sql_file = _write(
        tmp_path / "results.sql",
        """
CREATE TABLE events(value VARCHAR);
-- quackframe: log-result
INSERT INTO events VALUES ('é') RETURNING value;
""".strip(),
    )
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="persistent", path=database_path),
    )

    run([sql_file], config=config)

    assert capsys.readouterr().out.count("é") == 1
    with duckdb.connect(str(database_path)) as connection:
        assert connection.execute("SELECT value FROM events").fetchall() == [("é",)]


def test_all_returning_after_unicode_emits_and_executes_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "results.duckdb"
    sql_file = _write(
        tmp_path / "results.sql",
        """
CREATE TABLE events(value VARCHAR);
INSERT INTO events VALUES ('é') RETURNING value;
""".strip(),
    )
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="persistent", path=database_path),
        log_setting="all",
    )

    run([sql_file], config=config)

    assert capsys.readouterr().out.count("é") == 1
    with duckdb.connect(str(database_path)) as connection:
        assert connection.execute("SELECT value FROM events").fetchall() == [("é",)]


def test_returning_inside_nested_block_comment_is_not_a_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        """
CREATE TABLE events(value INTEGER);
INSERT INTO events VALUES (1) /* outer /* inner */ RETURNING */;
""".strip(),
    )

    run(
        [sql_file],
        config=QuackframeConfig(root=tmp_path, log_setting="all"),
    )

    assert capsys.readouterr().out == ""


def test_prepared_statements_do_not_change_when_source_file_changes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = _write(tmp_path / "results.sql", "SELECT 'prepared-value';")
    config = QuackframeConfig(root=tmp_path, log_setting="all")
    prepared = prepare_sql_files(
        [sql_file],
        root=tmp_path,
        log_setting=config.log_setting,
    )
    sql_file.write_text("SELECT 'changed-value';", encoding="utf-8")

    execute_plan(prepared, config)

    output = capsys.readouterr().out
    assert "prepared-value" in output
    assert "changed-value" not in output


def test_preparation_reports_the_invalid_annotation_statement(
    tmp_path: Path,
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        """
CREATE TABLE events(value INTEGER);
-- quackframe: log-result
-- another comment
SELECT 1;
""".strip(),
    )

    with pytest.raises(ExecutionError) as captured:
        prepare_sql_files(
            [sql_file],
            root=tmp_path,
            log_setting="annotations-only",
        )

    assert captured.value.statement_number == 2


def test_external_result_policy_is_supplied_by_the_runtime(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql_file = _write(
        tmp_path / "results.sql",
        "-- quackframe: log-result\nSELECT 'local-value';",
    )
    local_runtime = RuntimeRegistration(
        name="local-observer",
        module_name="quackframe.engine",
        implementation_name="execute_plan",
        result_logging_is_external=False,
    )
    monkeypatch.setattr(
        runtime_registry,
        "RUNTIME_REGISTRY",
        (*runtime_registry.RUNTIME_REGISTRY, local_runtime),
    )
    config = QuackframeConfig(root=tmp_path, runtime="local-observer")

    run([sql_file], config=config)

    assert "local-value" in capsys.readouterr().out


def test_external_runtime_requires_permission_before_sql(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "not-created.duckdb"
    sql_file = _write(
        tmp_path / "results.sql",
        "-- quackframe: log-result\nSELECT 1;",
    )
    config = QuackframeConfig(
        root=tmp_path,
        runtime="prefect",
        database=DatabaseConfig(mode="persistent", path=database_path),
    )

    with pytest.raises(ConfigurationError, match="External result logging"):
        run([sql_file], config=config)

    assert not database_path.exists()


def test_all_requires_external_permission_even_without_annotations(
    tmp_path: Path,
) -> None:
    sql_file = _write(tmp_path / "results.sql", "CREATE TABLE example(i INTEGER);")
    config = QuackframeConfig(
        root=tmp_path,
        runtime="prefect",
        log_setting="all",
    )

    with pytest.raises(ConfigurationError, match="External result logging"):
        run([sql_file], config=config)
