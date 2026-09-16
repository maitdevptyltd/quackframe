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
    """Open one configured session and clean up only Quackframe-owned files."""

    database_path, managed_path = _database_path(config)
    connection: DuckDBPyConnection | None = None

    try:
        connection = _open_connection(database_path, config)
        _load_extensions(connection, config.duckdb.extensions)
        yield connection
    finally:
        if connection is not None:
            connection.close()
        if managed_path is not None:
            _remove_managed_database(managed_path)


def _open_connection(
    database_path: str,
    config: QuackframeConfig,
) -> DuckDBPyConnection:
    try:
        return duckdb.connect(
            database=database_path,
            config=dict(config.duckdb.settings),
        )
    except Exception as error:
        raise ConfigurationError(
            f"DuckDB database could not be opened: {safe_error_reason(error)}"
        ) from None


def _database_path(config: QuackframeConfig) -> tuple[str, Path | None]:
    if config.database.mode == "memory":
        return ":memory:", None

    if config.database.mode == "persistent":
        path = config.database.path
        if path is None:  # Guarded by configuration validation.
            raise ConfigurationError("Persistent database mode requires a path")
        _prepare_parent(path)
        return str(path), None

    temporary_root = config.root / ".quackframe" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    path = config.database.path or temporary_root / f"{uuid4().hex}.duckdb"
    resolved_path = path.resolve()

    if config.database.path is not None and not resolved_path.is_relative_to(
        config.root
    ):
        raise ConfigurationError(
            "A temporary database path must remain inside the runtime root"
        )
    if resolved_path.exists():
        raise ConfigurationError(
            f"Temporary database path already exists and will not be overwritten: "
            f"{resolved_path}"
        )

    _prepare_parent(resolved_path)
    return str(resolved_path), resolved_path


def _prepare_parent(path: Path) -> None:
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
    try:
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}.wal").unlink(missing_ok=True)
    except OSError as error:
        raise ConfigurationError(
            f"Temporary database could not be removed: {path}: {error}"
        ) from None
