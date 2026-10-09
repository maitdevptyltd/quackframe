"""Prepare SQL once inside the selected execution environment."""

from collections.abc import Iterable

from quackframe.config import QuackframeConfig
from quackframe.runtimes.registry import get_runtime_registration
from quackframe.sql import (
    PreparedSqlFile,
    prepare_sql_files,
    validate_external_result_logging,
)


def prepare_execution(
    sql_files: Iterable[str], config: QuackframeConfig
) -> tuple[PreparedSqlFile, ...]:
    """Read and validate every file before the engine opens a database."""

    runtime = get_runtime_registration(config.runtime)
    prepared = prepare_sql_files(
        sql_files, root=config.root, log_setting=config.log_setting
    )
    validate_external_result_logging(
        prepared,
        config,
        result_logging_is_external=runtime.result_logging_is_external,
    )
    return prepared
