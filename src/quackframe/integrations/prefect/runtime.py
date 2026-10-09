"""Prefect wrappers around Quackframe's existing execution functions."""

from duckdb import DuckDBPyConnection
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE
from prefect.client.orchestration import get_client
from prefect.context import FlowRunContext

from quackframe.config import QuackframeConfig, load_config
from quackframe.engine import execute_plan
from quackframe.errors import ConfigurationError, QuackframeError, safe_error_reason
from quackframe.models import ExecutionResult, SqlFileResult
from quackframe.runtimes.preparation import prepare_execution
from quackframe.sql import (
    PreparedSqlFile,
    execute_sql_file,
    result_logging_can_emit,
)

_RETENTION_WARNING = (
    "Quackframe result logging is enabled; returned values may be retained "
    "by the destination logging system."
)


@task(cache_policy=NO_CACHE, retries=0, persist_result=False)
def execute_sql_file_task(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    """Show one SQL file as a non-cached Prefect task.

    The task receives the existing live DuckDB connection, preserving the
    same database session across the ordered file list.
    """

    logger = get_run_logger()
    return execute_sql_file(
        connection,
        sql_file,
        emit_result=lambda rendered_result: logger.info("\n%s", rendered_result),
    )


@flow(name="quackframe-run", retries=0, persist_result=False)
def quackframe_flow(
    sql_files: list[str],
    *,
    config_path: str | None = None,
    config: QuackframeConfig | None = None,
) -> ExecutionResult:
    """Run SQL paths sequentially in one DuckDB session, stopping on failure.

    Paths refer to the execution environment. By default, load project and
    environment settings using QUACKFRAME_ROOT, or the working directory.
    config_path selects alternate TOML; config supplies complete settings
    instead. These optional inputs are mutually exclusive.
    """

    if config is not None and config_path is not None:
        raise ConfigurationError("Supply either config or config_path, not both")
    resolved_config = config or load_config(config_path=config_path, runtime="prefect")
    if resolved_config.runtime != "prefect":
        raise ConfigurationError("quackframe_flow requires config.runtime='prefect'")

    _set_project_run_name(resolved_config)
    prepared = prepare_execution(sql_files, resolved_config)
    if resolved_config.allow_external_result_logging and result_logging_can_emit(
        prepared
    ):
        get_run_logger().warning(_RETENTION_WARNING)
    return execute_plan(
        prepared, resolved_config, execute_file=_execute_named_file_task
    )


def execute_with_prefect(
    sql_files: tuple[str, ...],
    config: QuackframeConfig,
) -> ExecutionResult:
    """Run Quackframe with an optional project name in Prefect.

    The flow name remains ``quackframe-run`` for every invocation. When the
    downstream ``pyproject.toml`` supplied a project name, Prefect uses it for
    the individual flow run instead.
    """

    try:
        return quackframe_flow(list(sql_files), config=config)
    except QuackframeError:
        raise
    except Exception as error:
        raise QuackframeError(
            f"Prefect runtime failed: {safe_error_reason(error)}"
        ) from None


def _set_project_run_name(config: QuackframeConfig) -> None:
    """Name this run after loading worker settings, preserving native overrides."""

    context = FlowRunContext.get()
    if (
        config.project_name is None
        or context is None
        or context.flow_run is None
        or context.flow is None
        or context.flow.flow_run_name is not None
    ):
        return

    # Update only this run: deployments load configuration after Prefect has
    # created it, and other runs may share the same imported flow object.
    with get_client(sync_client=True) as client:
        client.set_flow_run_name(context.flow_run.id, config.project_name)
    context.flow_run.name = config.project_name


def _execute_named_file_task(
    connection: DuckDBPyConnection,
    sql_file: PreparedSqlFile,
) -> SqlFileResult:
    """Name one Prefect task from its SQL path stem and execute it in order."""

    named_task = execute_sql_file_task.with_options(name=sql_file.path.stem)
    return named_task(connection, sql_file)
