"""Run ordered SQL paths without an external orchestrator."""

from quackframe.config import QuackframeConfig
from quackframe.engine import execute_plan
from quackframe.models import ExecutionResult
from quackframe.runtimes.preparation import prepare_execution


def execute_direct(
    sql_files: tuple[str, ...], config: QuackframeConfig
) -> ExecutionResult:
    """Prepare files in this process and execute them in one session."""

    return execute_plan(prepare_execution(sql_files, config), config)
