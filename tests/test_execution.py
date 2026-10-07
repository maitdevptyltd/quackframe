"""Ordered SQL execution and database lifecycle tests."""

from pathlib import Path

import duckdb
import pytest

from quackframe import (
    ConfigurationError,
    DatabaseConfig,
    ExecutionError,
    QuackframeConfig,
    run,
)
from quackframe.engine import execute_plan
from quackframe.runtimes import registry as runtime_registry
from quackframe.runtimes.registry import RuntimeRegistration
from quackframe.sql import prepare_sql_files


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
    database_path = tmp_path / "managed" / "temporary.duckdb"
    sql_file = _write(tmp_path / "run.sql", "CREATE TABLE example(value INTEGER);")
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="temporary", path=database_path),
    )

    run([sql_file], config=config)

    assert not database_path.exists()


def test_temporary_database_never_overwrites_an_existing_file(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "existing.duckdb"
    database_path.write_text("owned by caller", encoding="utf-8")
    sql_file = _write(tmp_path / "run.sql", "SELECT 1;")
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="temporary", path=database_path),
    )

    with pytest.raises(ConfigurationError, match="already exists"):
        run([sql_file], config=config)

    assert database_path.read_text(encoding="utf-8") == "owned by caller"


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
