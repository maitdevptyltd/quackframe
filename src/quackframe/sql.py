"""Validate and execute caller-ordered SQL files safely."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from duckdb import (
    DuckDBPyConnection,
    Statement,
    StatementType,
    extract_statements,
    token_type,
    tokenize,
)

from quackframe.config import LogSetting, QuackframeConfig
from quackframe.errors import ConfigurationError, ExecutionError, safe_error_reason
from quackframe.models import SqlFileResult

ResultEmitter = Callable[[str], None]

_LOG_RESULT_ANNOTATION = "quackframe: log-result"
_RETURNING_STATEMENT_TYPES = {
    StatementType.INSERT,
    StatementType.UPDATE,
    StatementType.DELETE,
}


@dataclass(frozen=True)
class PreparedSqlStatement:
    """Hold one DuckDB statement and its resolved result-logging decision."""

    statement: Statement
    emit_result: bool


@dataclass(frozen=True)
class PreparedSqlFile:
    """Hold immutable statement analysis ready for ordered execution."""

    path: Path
    statements: tuple[PreparedSqlStatement, ...]


def prepare_sql_files(
    sql_files: Iterable[str | Path],
    *,
    root: Path,
    log_setting: LogSetting,
) -> tuple[PreparedSqlFile, ...]:
    """Validate an ordered SQL-file list before opening DuckDB.

    Relative paths resolve from the runtime root. Reading every file here makes
    missing, empty, or invalid inputs fail before Quackframe creates a database.
    """

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

        statement_number: int | None = None
        try:
            statements = extract_statements(_read_sql(path))
            if not statements:
                raise ValueError("SQL file contains no executable statements")
            prepared_statements: list[PreparedSqlStatement] = []
            for next_statement_number, statement in enumerate(statements, start=1):
                statement_number = next_statement_number
                prepared_statements.append(
                    PreparedSqlStatement(
                        statement=statement,
                        emit_result=_should_emit_result(statement, log_setting),
                    )
                )
        except ConfigurationError:
            raise
        except Exception as error:
            raise ExecutionError(
                sql_file=path,
                statement_number=statement_number,
                reason=safe_error_reason(error),
            ) from None

        prepared.append(
            PreparedSqlFile(path=path, statements=tuple(prepared_statements))
        )

    return tuple(prepared)


def execute_sql_file(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
    *,
    emit_result: ResultEmitter | None = None,
) -> SqlFileResult:
    """Execute every parsed statement in one file on the shared connection.

    DuckDB's parser determines statement boundaries. Quackframe retains only a
    count and safe failure location, never full SQL or returned rows.
    """

    started_at = datetime.now(UTC)
    statement_number: int | None = None

    try:
        for next_statement_number, prepared in enumerate(sql_file.statements, start=1):
            statement_number = next_statement_number
            if prepared.emit_result:
                relation = connection.sql(prepared.statement)
                (emit_result or _print_result)(str(relation))
            else:
                connection.execute(prepared.statement)
    except Exception as error:  # DuckDB exposes several exception subclasses.
        raise ExecutionError(
            sql_file=sql_file.path,
            statement_number=statement_number,
            reason=safe_error_reason(error),
        ) from None

    return SqlFileResult(
        path=sql_file.path,
        statement_count=len(sql_file.statements),
        elapsed=datetime.now(UTC) - started_at,
    )


def validate_external_result_logging(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
    *,
    result_logging_is_external: bool,
) -> None:
    """Fail closed before an external destination can emit returned values."""

    if (
        result_logging_is_external
        and not config.allow_external_result_logging
        and (config.log_setting == "all" or result_logging_can_emit(sql_files))
    ):
        raise ConfigurationError(
            "External result logging is disabled; use "
            "--allow-external-result-logging or set "
            "QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING=true"
        )


def result_logging_can_emit(
    sql_files: tuple[PreparedSqlFile, ...],
) -> bool:
    """Return whether any prepared statement can emit a result."""

    return any(
        statement.emit_result
        for sql_file in sql_files
        for statement in sql_file.statements
    )


def _should_emit_result(statement: Statement, log_setting: LogSetting) -> bool:
    """Apply the resolved selection rule to one DuckDB-parsed statement."""

    if log_setting == "none":
        return False

    annotation_state = _annotation_state(statement.query)
    if annotation_state == "misplaced":
        raise ValueError(
            "The quackframe result annotation must be the final comment "
            "immediately before its statement"
        )

    result_producing = _is_result_producing(statement)
    if annotation_state == "selected" and not result_producing:
        raise ValueError(
            "The quackframe result annotation requires a result-producing statement"
        )
    return result_producing and (log_setting == "all" or annotation_state == "selected")


def _is_result_producing(statement: Statement) -> bool:
    """Recognise the accepted query and data-change result forms."""

    if statement.type == StatementType.SELECT:
        return True
    return statement.type in _RETURNING_STATEMENT_TYPES and _contains_sql_keyword(
        statement.query, "returning"
    )


def _annotation_state(query: str) -> str:
    """Classify an exact annotation among a statement's leading comments."""

    comments = _leading_comments(query)
    annotated = tuple(
        index
        for index, comment in enumerate(comments)
        if comment.strip() == _LOG_RESULT_ANNOTATION
    )
    if not annotated:
        return "none"
    if annotated[-1] == len(comments) - 1:
        return "selected"
    return "misplaced"


def _leading_comments(query: str) -> tuple[str, ...]:
    """Read only comments before executable SQL in a DuckDB statement."""

    comments: list[str] = []
    position = 0
    while position < len(query):
        while position < len(query) and query[position].isspace():
            position += 1

        if query.startswith("--", position):
            end = query.find("\n", position + 2)
            if end == -1:
                end = len(query)
            comments.append(query[position + 2 : end])
            position = end
            continue

        if query.startswith("/*", position):
            end = query.find("*/", position + 2)
            if end == -1:
                return tuple(comments)
            comments.append(query[position + 2 : end])
            position = end + 2
            continue

        break
    return tuple(comments)


def _contains_sql_keyword(query: str, keyword: str) -> bool:
    """Find one keyword using DuckDB's own SQL tokenization rules."""

    query_bytes = query.encode("utf-8")
    expected = keyword.casefold().encode("ascii")
    return any(
        kind == token_type.keyword
        and query_bytes[position : position + len(expected)].lower() == expected
        for position, kind in tokenize(query)
    )


def _print_result(rendered_result: str) -> None:
    """Write one native DuckDB relation rendering to direct output."""

    print(rendered_result)


def _read_sql(path: Path) -> str:
    """Read one non-empty UTF-8 SQL file with an actionable path on failure."""

    try:
        sql = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(f"Could not read SQL file: {path}: {error}") from None
    if not sql.strip():
        raise ConfigurationError(f"SQL file is empty: {path}")
    return sql
