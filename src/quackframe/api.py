"""Public Python entry point."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quackframe.config import QuackframeConfig, load_config
from quackframe.models import ExecutionResult
from quackframe.runtimes.registry import get_runtime
from quackframe.sql import prepare_sql_files


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
    prepared_files = prepare_sql_files(sql_files, root=resolved_config.root)
    runtime = get_runtime(resolved_config.runtime)
    return runtime(prepared_files, resolved_config)
