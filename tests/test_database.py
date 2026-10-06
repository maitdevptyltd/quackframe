"""Temporary database ownership across overlapping invocations."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from duckdb import CatalogException, DuckDBPyConnection

from quackframe import ConfigurationError, DatabaseConfig, QuackframeConfig, database


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
