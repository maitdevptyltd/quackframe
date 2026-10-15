"""Run SQL files through Quackframe's shared execution path."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from time import perf_counter

from duckdb import DuckDBPyConnection

from quackframe.config import QuackframeConfig
from quackframe.database import open_duckdb_session
from quackframe.models import ExecutionResult, SqlFileResult
from quackframe.resources import SessionResources
from quackframe.runtimes.registry import allows_error_details
from quackframe.sql import PreparedSqlFile, execute_sql_file
from quackframe.sql_functions.installer import install_functions

FileExecutor = Callable[
    [DuckDBPyConnection, PreparedSqlFile],
    SqlFileResult,
]


def execute_plan(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
    *,
    execute_file: FileExecutor = execute_sql_file,
) -> ExecutionResult:
    """Run validated files serially in one owned DuckDB session.

    Enabled SQL functions are installed before project SQL begins. The supplied
    file executor may add runtime observation, but it must execute each file in
    order against this same live connection.
    """

    started_at = perf_counter()
    file_results: list[SqlFileResult] = []

    # One run owns exactly one database session. Optional runtimes may report
    # each file separately, but every file must keep using this connection.
    with (
        open_duckdb_session(config) as connection,
        SessionResources(connection) as resources,
    ):
        install_functions(
            connection,
            config.functions.enabled,
            resources,
            include_error_details=allows_error_details(config),
        )
        for sql_file in sql_files:
            file_results.append(execute_file(connection, sql_file))

    return ExecutionResult(
        runtime=config.runtime,
        database_mode=config.database.mode,
        files=tuple(file_results),
        elapsed=timedelta(seconds=perf_counter() - started_at),
    )
