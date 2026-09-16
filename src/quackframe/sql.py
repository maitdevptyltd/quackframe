"""Validate and execute caller-ordered SQL files safely."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from duckdb import DuckDBPyConnection

from quackframe.errors import ConfigurationError, ExecutionError, safe_error_reason
from quackframe.models import SqlFileResult


@dataclass(frozen=True)
class PreparedSqlFile:
    """A validated SQL path ready for execution."""

    path: Path


def prepare_sql_files(
    sql_files: Iterable[str | Path],
    *,
    root: Path,
) -> tuple[PreparedSqlFile, ...]:
    """Resolve a non-empty ordered SQL-file list before opening DuckDB."""

    supplied_paths = tuple(Path(path) for path in sql_files)
    if not supplied_paths:
        raise ConfigurationError("At least one SQL file is required")

    prepared: list[PreparedSqlFile] = []
    for supplied_path in supplied_paths:
        path = supplied_path if supplied_path.is_absolute() else root / supplied_path
        path = path.resolve()
        if path.suffix.casefold() != ".sql":
            raise ConfigurationError(f"Expected a .sql file: {path}")
        if not path.is_file():
            raise ConfigurationError(f"SQL file does not exist: {path}")

        _read_sql(path)
        prepared.append(PreparedSqlFile(path=path))

    return tuple(prepared)


def execute_sql_file(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    """Execute every parsed statement in one file without retaining query data."""

    started_at = datetime.now(UTC)
    statement_number: int | None = None

    try:
        statements = connection.extract_statements(_read_sql(sql_file.path))
        if not statements:
            raise ValueError("SQL file contains no executable statements")

        for next_statement_number, statement in enumerate(statements, start=1):
            statement_number = next_statement_number
            connection.execute(statement)
    except Exception as error:  # DuckDB exposes several exception subclasses.
        raise ExecutionError(
            sql_file=sql_file.path,
            statement_number=statement_number,
            reason=safe_error_reason(error),
        ) from None

    return SqlFileResult(
        path=sql_file.path,
        statement_count=len(statements),
        elapsed=datetime.now(UTC) - started_at,
    )


def _read_sql(path: Path) -> str:
    try:
        sql = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(f"Could not read SQL file: {path}: {error}") from None
    if not sql.strip():
        raise ConfigurationError(f"SQL file is empty: {path}")
    return sql
