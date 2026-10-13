"""Generated temporary database ownership and cleanup."""

from pathlib import Path

import pytest
from duckdb import CatalogException, DuckDBPyConnection

from quackframe import (
    ConfigurationError,
    DatabaseConfig,
    ExecutionError,
    QuackframeConfig,
    database,
    run,
)
from quackframe.cli import main


def test_overlapping_temporary_sessions_use_distinct_generated_paths(
    tmp_path: Path,
) -> None:
    config = QuackframeConfig(root=tmp_path, database=DatabaseConfig(mode="temporary"))
    temporary_root = tmp_path / ".quackframe" / "tmp"

    with database.open_duckdb_session(config) as first:
        first.execute("CREATE TABLE example(value INTEGER)")
        (first_path,) = temporary_root.glob("*.duckdb")
        with database.open_duckdb_session(config) as second:
            second.execute("CREATE TABLE example(value INTEGER)")
            paths = set(temporary_root.glob("*.duckdb"))
            assert len(paths) == 2
            assert first_path in paths
            assert not list(temporary_root.glob("*.quackframe-lock"))
        assert list(temporary_root.glob("*.duckdb")) == [first_path]
        assert first.execute("SELECT count(*) FROM example").fetchone() == (0,)
    assert not list(temporary_root.iterdir())


def test_temporary_database_and_remaining_wal_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = QuackframeConfig(root=tmp_path, database=DatabaseConfig(mode="temporary"))
    remove_database = database._remove_managed_database  # pyright: ignore[reportPrivateUsage]

    def cleanup_with_wal(path: Path) -> None:
        path.with_suffix(".duckdb.wal").write_bytes(b"owned WAL")
        remove_database(path)

    monkeypatch.setattr(database, "_remove_managed_database", cleanup_with_wal)
    with database.open_duckdb_session(config) as connection:
        connection.execute("CREATE TABLE example(value INTEGER)")
    assert not list((tmp_path / ".quackframe" / "tmp").iterdir())


def test_default_temporary_directory_failure_has_configuration_cli_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".quackframe").write_text("caller-owned", encoding="utf-8")
    sql_file = tmp_path / "run.sql"
    sql_file.write_text("SELECT 42", encoding="utf-8")

    assert main(["run", str(sql_file), "--root", str(tmp_path), "--temporary"]) == 2
    error = capsys.readouterr().err
    assert "Could not prepare database directory" in error
    assert "Traceback" not in error


def test_failed_connection_removes_partial_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary")
    )

    def fail_open(path: str, config: QuackframeConfig) -> DuckDBPyConnection:
        Path(path).write_bytes(b"partial database")
        Path(f"{path}.wal").write_bytes(b"partial WAL")
        raise ConfigurationError("Connection failed")

    with monkeypatch.context() as patch:
        patch.setattr(database, "_open_connection", fail_open)
        with (
            pytest.raises(ConfigurationError, match="Connection failed"),
            database.open_duckdb_session(config),
        ):
            pytest.fail("Connection unexpectedly opened")

    with database.open_duckdb_session(config) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
    assert not list((tmp_path / ".quackframe" / "tmp").iterdir())


def test_sql_failure_removes_temporary_files(tmp_path: Path) -> None:
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary")
    )
    with (
        pytest.raises(CatalogException, match="missing_table"),
        database.open_duckdb_session(config) as connection,
    ):
        connection.execute("SELECT * FROM missing_table")
    assert not list(tmp_path.rglob("*.duckdb*"))


@pytest.mark.parametrize("cleanup_step", ["database", "wal"])
@pytest.mark.parametrize("sql_fails", [False, True])
def test_cleanup_failure_preserves_execution_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_step: str,
    sql_fails: bool,
) -> None:
    sql_file = tmp_path / "run.sql"
    sql_file.write_text(
        "SELECT 1; SELECT * FROM missing_table" if sql_fails else "SELECT 1",
        encoding="utf-8",
    )
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary")
    )
    original_unlink = Path.unlink

    def fail_unlink(target: Path, missing_ok: bool = False) -> None:
        suffix = ".duckdb" if cleanup_step == "database" else ".wal"
        if target.suffix == suffix:
            raise OSError("sensitive cleanup detail")
        original_unlink(target, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    if sql_fails:
        with pytest.raises(ExecutionError) as captured:
            run([sql_file], config=config)
        assert captured.value.sql_file == sql_file
        assert captured.value.statement_number == 2
        assert len(captured.value.__notes__) == 1
        assert "could not be" in captured.value.__notes__[0]
        assert "sensitive cleanup detail" not in captured.value.__notes__[0]
    else:
        with pytest.raises(ConfigurationError, match="could not be") as cleanup_failure:
            run([sql_file], config=config)
        assert "sensitive cleanup detail" not in str(cleanup_failure.value)


def test_failed_database_cleanup_keeps_sql_cli_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sql_file = tmp_path / "run.sql"
    sql_file.write_text("SELECT * FROM missing_table", encoding="utf-8")

    def fail_cleanup(path: Path) -> None:
        raise ConfigurationError("Temporary database could not be removed")

    monkeypatch.setattr(database, "_remove_managed_database", fail_cleanup)
    assert main(["run", str(sql_file), "--root", str(tmp_path), "--temporary"]) == 1
    assert "statement 1" in capsys.readouterr().err


@pytest.mark.parametrize("interrupted", [False, True])
def test_cleanup_failure_preserves_setup_or_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary")
    )
    primary_error = (
        KeyboardInterrupt() if interrupted else ConfigurationError("Setup failed")
    )

    def fail_cleanup(path: Path) -> None:
        raise ConfigurationError("Temporary database could not be removed")

    monkeypatch.setattr(database, "_remove_managed_database", fail_cleanup)
    with (
        pytest.raises(type(primary_error)) as captured,
        database.open_duckdb_session(config),
    ):
        raise primary_error

    assert captured.value is primary_error
    assert len(primary_error.__notes__) == 1
    assert "could not be removed" in primary_error.__notes__[0]
    assert "sensitive cleanup detail" not in " ".join(primary_error.__notes__)
