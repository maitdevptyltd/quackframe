"""Resolve runtime functions without importing optional frameworks in core."""

from collections.abc import Callable
from importlib import import_module
from typing import cast

from quackframe.config import QuackframeConfig
from quackframe.engine import execute_plan
from quackframe.errors import OptionalDependencyError
from quackframe.models import ExecutionResult
from quackframe.sql import PreparedSqlFile

Runtime = Callable[
    [tuple[PreparedSqlFile, ...], QuackframeConfig],
    ExecutionResult,
]


def get_runtime(name: str) -> Runtime:
    """Return the selected runtime function."""

    if name == "direct":
        return execute_plan
    if name == "prefect":
        return _load_prefect_runtime()
    raise OptionalDependencyError(f"Unsupported runtime: {name}")


def _load_prefect_runtime() -> Runtime:
    try:
        module = import_module("quackframe.integrations.prefect.runtime")
    except ModuleNotFoundError as error:
        if error.name == "prefect":
            raise OptionalDependencyError(
                "The Prefect runtime requires 'quackframe[prefect]'"
            ) from None
        raise
    return cast(Runtime, module.execute_with_prefect)
