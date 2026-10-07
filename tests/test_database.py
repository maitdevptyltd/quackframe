"""Temporary database ownership across overlapping invocations."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

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


@pytest.mark.parametrize("blocked_default", [False, True])
def test_explicit_temporary_path_does_not_prepare_default_directory(
    tmp_path: Path, blocked_default: bool
) -> None:
    default_directory = tmp_path / ".quackframe"
    if blocked_default:
        default_directory.write_text("caller-owned", encoding="utf-8")
    path = tmp_path / "custom" / "run.duckdb"
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )

    with database.open_duckdb_session(config) as connection:
        assert connection.execute("SELECT 42").fetchone() == (42,)
        assert path.is_file()

    assert not list(path.parent.glob("run.duckdb*"))
    if blocked_default:
        assert default_directory.read_text(encoding="utf-8") == "caller-owned"
    else:
        assert not default_directory.exists()


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


@pytest.mark.parametrize("separate_process", [False, True])
def test_temporary_path_is_reserved_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, separate_process: bool
) -> None:
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="temporary", path=tmp_path / "shared.duckdb"),
    )
    opening = Event()
    proceed = Event()
    open_connection = database._open_connection  # pyright: ignore[reportPrivateUsage]

    def paused_open(path: str, config: QuackframeConfig) -> DuckDBPyConnection:
        if not opening.is_set():
            opening.set()
            assert proceed.wait(timeout=10)
        return open_connection(path, config)

    def owner() -> None:
        with database.open_duckdb_session(config) as connection:
            assert connection.execute("SELECT 42").fetchone() == (42,)

    monkeypatch.setattr(database, "_open_connection", paused_open)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(owner)
        try:
            assert opening.wait(timeout=10)
            if separate_process:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; import sys; "
                        "from quackframe import DatabaseConfig, QuackframeConfig; "
                        "from quackframe.database import open_duckdb_session; "
                        "root = Path(sys.argv[1]); "
                        "config = QuackframeConfig(root=root, database=DatabaseConfig("
                        "mode='temporary', path=root / 'shared.duckdb')); "
                        "\nwith open_duckdb_session(config): pass",
                        str(tmp_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                assert result.returncode != 0
                assert "already reserved" in result.stderr
            else:
                with (
                    pytest.raises(ConfigurationError, match="reserved"),
                    database.open_duckdb_session(config),
                ):
                    pytest.fail("A competing invocation acquired the same path")
        finally:
            proceed.set()
            running.result(timeout=10)

    assert not (tmp_path / "shared.duckdb").exists()
    assert not (tmp_path / "shared.duckdb.quackframe-lock").exists()


def test_reservation_covers_database_and_wal_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "shared.duckdb"
    wal = tmp_path / "shared.duckdb.wal"
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )
    remove_database = database._remove_managed_database  # pyright: ignore[reportPrivateUsage]

    def checked_cleanup(managed_path: Path) -> None:
        # The connection has closed; stand in for a WAL still awaiting removal.
        wal.write_bytes(b"owned WAL")
        contents = path.read_bytes()
        with (
            pytest.raises(ConfigurationError, match="reserved"),
            database.open_duckdb_session(config),
        ):
            pytest.fail("Contender reached an owned database")
        assert path.read_bytes() == contents
        assert wal.read_bytes() == b"owned WAL"
        remove_database(managed_path)
        with (
            pytest.raises(ConfigurationError, match="reserved"),
            database.open_duckdb_session(config),
        ):
            pytest.fail("Reservation was released before cleanup returned")

    monkeypatch.setattr(database, "_remove_managed_database", checked_cleanup)
    with database.open_duckdb_session(config) as connection:
        connection.execute("CREATE TABLE example(value INTEGER)")
    assert not path.exists()
    assert not wal.exists()
    assert not path.with_name(f"{path.name}.quackframe-lock").exists()


@pytest.mark.parametrize("existing_suffix", ["", ".wal", ".quackframe-lock"])
def test_existing_files_are_never_adopted(tmp_path: Path, existing_suffix: str) -> None:
    path = tmp_path / "existing.duckdb"
    existing = path.with_name(f"{path.name}{existing_suffix}")
    existing.write_bytes(b"caller-owned")
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )
    with (
        pytest.raises(ConfigurationError, match="already"),
        database.open_duckdb_session(config),
    ):
        pytest.fail("Existing files were adopted")
    assert existing.read_bytes() == b"caller-owned"
    assert list(tmp_path.glob("existing.duckdb*")) == [existing]


def test_failed_connection_releases_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "retry.duckdb"
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )

    def fail_open(path: str, config: QuackframeConfig) -> DuckDBPyConnection:
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
    assert not list(tmp_path.glob("retry.duckdb*"))


@pytest.mark.parametrize("explicit_path", [False, True])
def test_sql_failure_removes_temporary_files_and_reservation(
    tmp_path: Path, explicit_path: bool
) -> None:
    path = tmp_path / "failed.duckdb" if explicit_path else None
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )
    with (
        pytest.raises(CatalogException, match="missing_table"),
        database.open_duckdb_session(config) as connection,
    ):
        connection.execute("SELECT * FROM missing_table")
    assert not list(tmp_path.rglob("*.duckdb*"))


@pytest.mark.parametrize("cleanup_step", ["database", "wal", "reservation"])
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
    path = tmp_path / "cleanup.duckdb"
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )
    original_unlink = Path.unlink
    original_rmdir = Path.rmdir

    def fail_unlink(target: Path, missing_ok: bool = False) -> None:
        suffix = ".duckdb" if cleanup_step == "database" else ".wal"
        if cleanup_step != "reservation" and target.suffix == suffix:
            raise OSError("sensitive cleanup detail")
        original_unlink(target, missing_ok=missing_ok)

    def fail_rmdir(target: Path) -> None:
        if target.name.endswith(".quackframe-lock"):
            raise OSError("sensitive cleanup detail")
        original_rmdir(target)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    if cleanup_step == "reservation":
        monkeypatch.setattr(Path, "rmdir", fail_rmdir)

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

    assert path.with_name(f"{path.name}.quackframe-lock").exists() == (
        cleanup_step == "reservation"
    )


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
def test_multiple_cleanup_failures_preserve_original_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    path = tmp_path / "interrupted.duckdb"
    config = QuackframeConfig(
        root=tmp_path, database=DatabaseConfig(mode="temporary", path=path)
    )
    primary_error = (
        KeyboardInterrupt() if interrupted else ConfigurationError("Setup failed")
    )

    def fail_cleanup(path: Path) -> None:
        raise ConfigurationError("Temporary database could not be removed")

    def fail_release(path: Path) -> None:
        raise OSError("sensitive cleanup detail")

    monkeypatch.setattr(database, "_remove_managed_database", fail_cleanup)
    monkeypatch.setattr(Path, "rmdir", fail_release)
    with (
        pytest.raises(type(primary_error)) as captured,
        database.open_duckdb_session(config),
    ):
        raise primary_error

    assert captured.value is primary_error
    assert len(primary_error.__notes__) == 2
    assert "could not be removed" in primary_error.__notes__[0]
    assert "could not be released" in primary_error.__notes__[1]
    assert "sensitive cleanup detail" not in " ".join(primary_error.__notes__)
