"""Public Python entry point."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quackframe.config import QuackframeConfig, load_config
from quackframe.models import ExecutionResult
from quackframe.runtimes.registry import get_runtime_registration


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
    paths = tuple(str(path) for path in sql_files)
    return runtime.load()(paths, resolved_config)
