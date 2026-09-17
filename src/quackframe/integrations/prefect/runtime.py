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
    """Show one SQL file as a non-cached Prefect task.

    The task receives the existing live DuckDB connection, preserving the
    same database session across the ordered file list.
    """

    return execute_sql_file(connection, sql_file)


@flow(name="quackframe-run", retries=0, persist_result=False)
def execute_plan_flow(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
) -> ExecutionResult:
    """Represent the stable Quackframe execution process as a Prefect flow."""

    return execute_plan(sql_files, config, execute_file=_execute_named_file_task)


def execute_with_prefect(
    sql_files: tuple[PreparedSqlFile, ...],
    config: QuackframeConfig,
) -> ExecutionResult:
    """Run Quackframe with an optional project name in Prefect.

    The flow name remains ``quackframe-run`` for every invocation. When the
    downstream ``pyproject.toml`` supplied a project name, Prefect uses it for
    the individual flow run instead.
    """

    configured_flow = execute_plan_flow
    if config.project_name is not None:
        configured_flow = execute_plan_flow.with_options(
            flow_run_name=config.project_name,
        )
    try:
        return configured_flow(sql_files, config)
    except ExecutionError:
        raise
    except Exception as error:
        raise QuackframeError(
            f"Prefect runtime failed: {safe_error_reason(error)}"
        ) from None

def _execute_named_file_task(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    """Name one Prefect task from its SQL path stem and execute it in order."""

    named_task = execute_sql_file_task.with_options(name=sql_file.path.stem)
    return named_task(connection, sql_file)
