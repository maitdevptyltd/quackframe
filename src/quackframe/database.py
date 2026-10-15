"""Own DuckDB connection setup and storage cleanup."""

from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import duckdb
from duckdb import DuckDBPyConnection

from quackframe.config import QuackframeConfig
from quackframe.errors import ConfigurationError, safe_error_reason

_EXTENSION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@contextmanager
def open_duckdb_session(
    config: QuackframeConfig,
) -> Generator[DuckDBPyConnection, None, None]:
    """Open one configured session and clean up Quackframe-owned files.

    Quackframe closes the connection in every database mode. It deletes files
    only for temporary databases created for this run.
    """

    database_path, managed_path = _database_path(config)
    connection: DuckDBPyConnection | None = None
    primary_error: BaseException | None = None
    try:
        connection = _open_connection(database_path, config)
        _load_extensions(connection, config.duckdb.extensions)
        yield connection
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if connection is not None:
            connection.close()
        # Persistent paths always remain caller-owned.
        if managed_path is not None:
            try:
                _remove_managed_database(managed_path)
            except ConfigurationError as error:
                _report_cleanup_failure(str(error), primary_error)


def _open_connection(
    database_path: str,
    config: QuackframeConfig,
) -> DuckDBPyConnection:
    """Open DuckDB with the final settings and report setup failures clearly."""

    try:
        return duckdb.connect(
            database=database_path,
            # Request diagnostics before lock_configuration can prevent SET.
            config={**config.duckdb.settings, "errors_as_json": "true"},
        )
    except Exception as error:
        raise ConfigurationError(
            f"DuckDB database could not be opened: {safe_error_reason(error)}"
        ) from None


def _database_path(config: QuackframeConfig) -> tuple[str, Path | None]:
    """Resolve storage and identify the generated file owned by this run."""

    if config.database.mode == "memory":
        return ":memory:", None

    if config.database.mode == "persistent":
        path = config.database.path
        if path is None:  # Guarded by configuration validation.
            raise ConfigurationError("Persistent database mode requires a path")
        _prepare_parent(path)
        return str(path), None

    path = config.root / ".quackframe" / "tmp" / f"{uuid4().hex}.duckdb"
    _prepare_parent(path)
    return str(path), path


def _prepare_parent(path: Path) -> None:
    """Create a database parent directory or report its exact failing path."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConfigurationError(
            f"Could not prepare database directory: {path.parent}: {error}"
        ) from None


def _load_extensions(
    connection: DuckDBPyConnection,
    extensions: tuple[str, ...],
) -> None:
    """Install and load explicitly configured DuckDB extensions in order."""

    for extension in extensions:
        if _EXTENSION_NAME.fullmatch(extension) is None:
            raise ConfigurationError(f"Invalid DuckDB extension name: {extension}")
        try:
            connection.execute(f'INSTALL "{extension}"')
            connection.execute(f'LOAD "{extension}"')
        except Exception as error:
            raise ConfigurationError(
                f"DuckDB extension '{extension}' could not be loaded: "
                f"{safe_error_reason(error)}"
            ) from None


def _remove_managed_database(path: Path) -> None:
    """Remove a Quackframe-owned temporary database and its possible WAL."""

    try:
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}.wal").unlink(missing_ok=True)
    except OSError:
        raise ConfigurationError(
            f"Temporary database could not be removed: {path}"
        ) from None


def _report_cleanup_failure(message: str, primary_error: BaseException | None) -> None:
    """Retain the original failure and attach only a safe cleanup diagnostic."""

    if primary_error is not None:
        primary_error.add_note(message)
    else:
        raise ConfigurationError(message) from None
