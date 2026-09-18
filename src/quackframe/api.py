"""Public Python entry point."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quackframe.config import QuackframeConfig, load_config
from quackframe.models import ExecutionResult
from quackframe.runtimes.registry import get_runtime_registration
from quackframe.sql import prepare_sql_files, validate_external_result_logging


def run(
    sql_files: Iterable[str | Path],
    *,
    config: QuackframeConfig | None = None,
) -> ExecutionResult:
    """Execute ordered SQL files through the configured runtime.

    Callers may supply a fully resolved configuration. Otherwise Quackframe
    loads project, environment, and default values from the current directory.
    Every runtime returns the same Quackframe result type.
    """

    resolved_config = config or load_config()
    runtime = get_runtime_registration(resolved_config.runtime)
    prepared_files = prepare_sql_files(
        sql_files,
        root=resolved_config.root,
        log_setting=resolved_config.log_setting,
    )
    validate_external_result_logging(
        prepared_files,
        resolved_config,
        result_logging_is_external=runtime.result_logging_is_external,
    )
    return runtime.load()(prepared_files, resolved_config)
