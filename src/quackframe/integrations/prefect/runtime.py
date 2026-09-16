"""Prefect wrappers around Quackframe's existing execution functions."""

from duckdb import DuckDBPyConnection
from prefect import flow, task
from prefect.cache_policies import NO_CACHE

from quackframe.config import QuackframeConfig
from quackframe.engine import execute_plan
from quackframe.errors import ExecutionError, QuackframeError, safe_error_reason
from quackframe.models import ExecutionResult, SqlFileResult
from quackframe.sql import PreparedSqlFile, execute_sql_file


@task(cache_policy=NO_CACHE, retries=0, persist_result=False)
def execute_sql_file_task(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    """Represent one existing Quackframe file execution as a Prefect task."""

    return execute_sql_file(connection, sql_file)


@flow(retries=0, persist_result=False)
def execute_plan_flow(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
) -> ExecutionResult:
    """Represent one existing Quackframe execution plan as a Prefect flow."""

    return execute_plan(sql_files, config, execute_file=_execute_named_file_task)


def execute_with_prefect(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
) -> ExecutionResult:
    """Run the decorated wrappers under a descriptive Prefect flow name."""

    named_flow = execute_plan_flow.with_options(
        name=_flow_name(sql_files, config),
    )
    try:
        return named_flow(sql_files, config)
    except ExecutionError:
        raise
    except Exception as error:
        raise QuackframeError(
            f"Prefect runtime failed: {safe_error_reason(error)}"
        ) from None


def _flow_name(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
) -> str:
    first_file = sql_files[0].path.stem
    if len(sql_files) == 1:
        return f"{config.root.name}: {first_file}"
    return f"{config.root.name}: {first_file} (+{len(sql_files) - 1} files)"


def _execute_named_file_task(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    named_task = execute_sql_file_task.with_options(name=sql_file.path.name)
    return named_task(connection, sql_file)
