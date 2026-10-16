"""Validate and execute caller-ordered SQL files safely."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from logging import INFO, Logger, LoggerAdapter, StreamHandler
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from duckdb import (
    DuckDBPyConnection,
    Statement,
    StatementType,
    connect,
    token_type,
    tokenize,
)

from quackframe.config import LogSetting, QuackframeConfig
from quackframe.errors import (
    ConfigurationError,
    ExecutionError,
    error_position,
    report_error_reason,
)
from quackframe.models import SqlFileResult

ResultEmitter = Callable[[str], None]

_LOG_RESULT_ANNOTATION = "quackframe: log-result"
_RETURNING_STATEMENT_TYPES = {
    StatementType.INSERT,
    StatementType.UPDATE,
    StatementType.DELETE,
}


class _SqlPreparationError(ValueError):
    """Carry only fixed Quackframe diagnostics for SQL preparation."""


@dataclass(frozen=True)
class PreparedSqlStatement:
    """Hold one DuckDB statement and its resolved result-logging decision."""

    statement: Statement
    emit_result: bool
    query: str
    source_offset: int


@dataclass(frozen=True)
class PreparedSqlFile:
    """Hold immutable statement analysis ready for ordered execution."""

    path: Path
    source: str
    statements: tuple[PreparedSqlStatement, ...]
    include_error_details: bool = True


def prepare_sql_files(
    sql_files: Iterable[str | Path],
    *,
    root: Path,
    log_setting: LogSetting,
    include_error_details: bool = True,
) -> tuple[PreparedSqlFile, ...]:
    """Validate an ordered SQL-file list before opening the execution database.

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

        source = _read_sql(path)
        statement_number: int | None = None
        offset = 0
        query = source
        failure: ExecutionError | None = None
        prepared_statements: list[PreparedSqlStatement] = []
        try:
            # DuckDB expands dynamic PIVOT into internal statements. Keep source
            # boundaries for attribution and execute each source statement whole.
            with connect(config={"errors_as_json": "true"}) as parser:
                for offset, query in _source_statements(source):
                    statement_number = len(prepared_statements) + 1
                    statements = parser.extract_statements(query)
                    if not statements:
                        continue
                    statement = statements[-1]
                    prepared_statements.append(
                        PreparedSqlStatement(
                            statement=statement,
                            emit_result=_should_emit_result(statement, log_setting),
                            query=query,
                            source_offset=offset,
                        )
                    )
            if not prepared_statements:
                raise _SqlPreparationError("SQL file contains no executable statements")
        except ConfigurationError:
            raise
        except Exception as error:
            line, column = _source_location(source, offset, query, error)
            failure = ExecutionError(
                sql_file=path,
                statement_number=statement_number,
                line=line,
                column=column,
                reason=(
                    str(error)
                    if isinstance(error, _SqlPreparationError)
                    else report_error_reason(
                        error, include_details=include_error_details
                    )
                ),
            )
        if failure is not None:
            raise failure from None

        prepared.append(
            PreparedSqlFile(
                path=path,
                source=source,
                statements=tuple(prepared_statements),
                include_error_details=include_error_details,
            )
        )

    return tuple(prepared)


def execute_sql_file(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
    *,
    emit_result: ResultEmitter | None = None,
    progress_logger: Logger | LoggerAdapter[Logger] | None = None,
    error_logger: Logger | LoggerAdapter[Logger] | None = None,
) -> SqlFileResult:
    """Execute every parsed statement in one file on the shared connection.

    Original source statements determine counts and locations, including PIVOT
    statements expanded internally by DuckDB. Failures omit SQL excerpts and rows.
    """

    logger = progress_logger if progress_logger is not None else _terminal_logger()
    started_at = perf_counter()
    logger.info("File started: %s", sql_file.path)
    statement_number: int | None = None
    prepared: PreparedSqlStatement | None = None
    statement_started_at = started_at
    failure: ExecutionError | None = None

    try:
        for next_statement_number, prepared in enumerate(sql_file.statements, start=1):
            statement_number = next_statement_number
            statement_started_at = perf_counter()
            logger.info("Statement %d started: %s", statement_number, sql_file.path)
            if prepared.emit_result:
                (emit_result or _print_result)(
                    _render_complete_result(connection, prepared.query)
                )
            else:
                connection.execute(prepared.query)
            logger.info(
                "Statement %d completed: %s (%.3fs)",
                statement_number,
                sql_file.path,
                perf_counter() - statement_started_at,
            )
    except Exception as error:  # DuckDB exposes several exception subclasses.
        failed_at = perf_counter()
        # Progress identifies the failed work; error conversion below owns detail
        # disclosure. Never attach the original exception to these log records.
        logger.error(
            "Statement %d failed: %s (%.3fs)",
            statement_number,
            sql_file.path,
            failed_at - statement_started_at,
        )
        logger.error("File failed: %s (%.3fs)", sql_file.path, failed_at - started_at)
        line, column = (
            _source_location(
                sql_file.source, prepared.source_offset, prepared.query, error
            )
            if prepared is not None
            else (None, None)
        )
        failure = ExecutionError(
            sql_file=sql_file.path,
            statement_number=statement_number,
            line=line,
            column=column,
            reason=report_error_reason(
                error,
                include_details=sql_file.include_error_details,
                error_logger=error_logger,
            ),
        )
    if failure is not None:
        raise failure from None

    elapsed = timedelta(seconds=perf_counter() - started_at)
    logger.info("File completed: %s (%.3fs)", sql_file.path, elapsed.total_seconds())
    return SqlFileResult(
        path=sql_file.path,
        statement_count=len(sql_file.statements),
        elapsed=elapsed,
    )


def _terminal_logger() -> Logger:
    """Report direct progress without changing the caller's logging setup."""

    logger = Logger("quackframe.progress", level=INFO)
    logger.addHandler(StreamHandler())
    return logger


def _render_complete_result(connection: DuckDBPyConnection, statement: str) -> str:
    """Materialize once in DuckDB, then render its bounded native preview."""

    # Rendering a lazy relation evaluates only a preview, and rendering after
    # execute() reruns it. Keep the complete result in a temporary DuckDB table.
    name = f"_quackframe_result_{uuid4().hex}"
    view = f"{name}_source"
    relation = connection.sql(statement)
    try:
        relation.query(view, f"CREATE TEMP TABLE {name} AS SELECT * FROM {view}")
        return str(connection.table(name))
    finally:
        connection.execute(f"DROP VIEW IF EXISTS {view}")
        connection.execute(f"DROP TABLE IF EXISTS {name}")


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
        raise _SqlPreparationError(
            "The quackframe result annotation must be the final comment "
            "immediately before its statement"
        )

    result_producing = _is_result_producing(statement)
    if annotation_state == "selected" and not result_producing:
        raise _SqlPreparationError(
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


def _source_statements(source: str) -> Iterable[tuple[int, str]]:
    """Split only semicolon tokens, preserving original bytes and comments."""

    encoded = source.encode("utf-8")
    start = 0
    for position, kind in tokenize(source):
        if kind == token_type.operator and encoded[position : position + 1] == b";":
            yield start, encoded[start : position + 1].decode("utf-8")
            start = position + 1
    if start < len(encoded):
        yield start, encoded[start:].decode("utf-8")


def _source_location(
    source: str, offset: int, query: str, error: Exception
) -> tuple[int | None, int | None]:
    """Translate only actual backend byte positions into original file coordinates."""

    position = error_position(error)
    if position is None or position > len(query.encode("utf-8")):
        return None, None
    try:
        prefix = source.encode("utf-8")[: offset + position].decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    return prefix.count("\n") + 1, len(prefix.rsplit("\n", 1)[-1]) + 1
