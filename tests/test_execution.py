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
