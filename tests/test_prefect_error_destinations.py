"""Exercise real Prefect logging and failed-state conversion offline."""

import asyncio
import io
import logging
import pickle
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import duckdb
import pytest

pytest.importorskip("prefect")
from prefect import get_run_logger
from prefect.client.schemas.objects import TaskRun
from prefect.context import TaskRunContext
from prefect.logging import handlers
from prefect.logging.loggers import patch_print
from prefect.settings import PREFECT_LOGGING_TO_API_ENABLED, temporary_settings
from prefect.states import exception_to_failed_state

from quackframe import QuackframeConfig
from quackframe.errors import QuackframeError
from quackframe.integrations.prefect import runtime
from quackframe.sql import prepare_sql_files

MARKER = "LOCAL_ONLY_TEST_42"


@pytest.fixture
def prefect_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[io.StringIO, list[dict[str, Any]]]]:
    terminal = io.StringIO()
    outgoing: list[dict[str, Any]] = []
    monkeypatch.setattr(handlers, "emit_api_log", outgoing.append)
    logger = logging.getLogger("prefect.task_runs")
    monkeypatch.setattr(
        logger,
        "handlers",
        [handlers.PrefectConsoleHandler(stream=terminal), handlers.APILogHandler()],
    )
    monkeypatch.setattr(logger, "propagate", False)
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "level", logging.INFO)

    # A real context gives get_run_logger its run metadata. No client or engine
    # is started: only the outbound API sink is intercepted.
    context = TaskRunContext.model_construct(
        task=runtime.execute_sql_file_task,
        task_run=TaskRun(
            name="offline-test",
            task_key="offline",
            dynamic_key="0",
            flow_run_id=uuid4(),
        ),
        log_prints=True,
    )
    with (
        temporary_settings({PREFECT_LOGGING_TO_API_ENABLED: True}),
        context,
        patch_print(),
    ):
        yield terminal, outgoing


def assert_destinations(
    error: QuackframeError,
    allow: bool,
    logs: tuple[io.StringIO, list[dict[str, Any]]],
) -> None:
    terminal, outgoing = logs
    # These are the formatting and state conversion used by the Prefect engine.
    state = asyncio.run(exception_to_failed_state(error))
    get_run_logger().error(
        "Run failed", exc_info=(type(error), error, error.__traceback__)
    )

    assert MARKER in terminal.getvalue()
    assert (MARKER in str(outgoing)) is allow
    assert (MARKER in (state.message or "")) is allow
    assert (MARKER.encode() in pickle.dumps(state.data)) is allow
    assert (MARKER in "".join(traceback.format_exception(error))) is allow
    assert error.__context__ is None
    assert error.__cause__ is None


@pytest.mark.parametrize("allow", [False, True])
def test_sql_error_console_and_api_destinations(
    tmp_path: Path, allow: bool, prefect_logs: tuple[io.StringIO, list[dict[str, Any]]]
) -> None:
    path = tmp_path / "failure.sql"
    path.write_text(f"SELECT CAST('{MARKER}' AS INTEGER)", encoding="utf-8")
    prepared = prepare_sql_files(
        [path], root=tmp_path, log_setting="none", include_error_details=allow
    )
    with (
        duckdb.connect(config={"errors_as_json": "true"}) as connection,
        pytest.raises(QuackframeError) as captured,
    ):
        runtime.execute_sql_file_task.fn(connection, prepared[0])
    assert_destinations(captured.value, allow, prefect_logs)


@pytest.mark.parametrize("allow", [False, True])
@pytest.mark.parametrize(
    "failure_path", ["connection", "extension", "installer", "setup"]
)
def test_setup_error_console_and_api_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow: bool,
    failure_path: str,
    prefect_logs: tuple[io.StringIO, list[dict[str, Any]]],
) -> None:
    from quackframe import database
    from quackframe.sql_functions import installer

    config = QuackframeConfig(
        root=tmp_path, runtime="prefect", allow_external_error_logging=allow
    )
    if failure_path == "connection":
        monkeypatch.setattr(
            database.duckdb, "connect", Mock(side_effect=duckdb.IOException(MARKER))
        )
    elif failure_path == "setup":
        monkeypatch.setattr(
            runtime, "execute_plan", Mock(side_effect=RuntimeError(MARKER))
        )
    else:
        connection = Mock()
        connection.execute.side_effect = duckdb.InvalidInputException(MARKER)
        monkeypatch.setattr(database, "_open_connection", Mock(return_value=connection))
        if failure_path == "extension":
            config.duckdb.extensions = ("json",)
        else:
            config.functions.enabled = ("test",)
            monkeypatch.setattr(installer, "resolve_functions", Mock(return_value=()))
    with pytest.raises(QuackframeError) as captured:
        runtime.execute_plan_flow.fn((), config)
    assert_destinations(captured.value, allow, prefect_logs)


def test_preparation_diagnostic_bypasses_print_capture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    prefect_logs: tuple[io.StringIO, list[dict[str, Any]]],
) -> None:
    path = tmp_path / "syntax.sql"
    path.write_text(f"SELECT 1 {MARKER} {MARKER}", encoding="utf-8")
    with pytest.raises(QuackframeError) as captured:
        prepare_sql_files(
            [path], root=tmp_path, log_setting="none", include_error_details=False
        )
    # DuckDB identifies the unexpected token in its complete parser diagnostic.
    assert MARKER in capsys.readouterr().err
    assert MARKER not in str(prefect_logs[1])
    assert MARKER not in str(captured.value)
    assert captured.value.__context__ is None
