"""Deployment execution tests use mocked Prefect requests and synthetic run states."""

import asyncio
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import duckdb
import pytest

pytest.importorskip("prefect")
from prefect import deployments
from prefect.client.schemas.objects import FlowRun, State
from prefect.settings import PREFECT_API_URL
from prefect.states import Cancelled, Completed, Crashed, Failed, Running

from quackframe import FunctionsConfig, QuackframeConfig, run
from quackframe.cli import main
from quackframe.errors import ExecutionError
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.prefect_run_deployment.function import (
    prefect_run_deployment,
)

DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(
        PREFECT_API_URL, "value", lambda: "http://prefect.example.test/api"
    )
    mocked = Mock(return_value=FlowRun(flow_id=uuid4(), id=uuid4(), state=Completed()))
    monkeypatch.setattr(deployments, "run_deployment", mocked)
    return mocked


def test_success_returns_run_id_and_uses_native_sync_wait(launch: Mock) -> None:
    assert prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID)) == str(
        launch.return_value.id
    )
    arguments = launch.call_args.kwargs
    assert arguments["name"] == DEPLOYMENT_ID
    assert arguments["timeout"] is None
    assert arguments["_sync"] is True
    assert arguments["as_subflow"] is True
    assert UUID(arguments["idempotency_key"])


def test_separate_sql_invocations_get_separate_idempotency_keys(launch: Mock) -> None:
    prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    keys = [call.kwargs["idempotency_key"] for call in launch.call_args_list]
    assert len(set(keys)) == 2


def test_sync_result_is_required_inside_an_async_caller(launch: Mock) -> None:
    async def caller() -> str:
        return prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))

    assert asyncio.run(caller()) == str(launch.return_value.id)
    assert launch.call_args.kwargs["_sync"] is True


@pytest.mark.parametrize("identifier", ["", "flow/prod", "not-a-uuid"])
def test_invalid_ids_do_not_launch(identifier: str | None, launch: Mock) -> None:
    with pytest.raises(ValueError, match="valid deployment UUID"):
        prefect_run_deployment(deployment_id=identifier)
    launch.assert_not_called()


def test_missing_server_does_not_launch_or_start_ephemeral_server(launch: Mock) -> None:
    with (
        patch.object(PREFECT_API_URL, "value", return_value=None),
        pytest.raises(ValueError, match="Configure PREFECT_API_URL"),
    ):
        prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    launch.assert_not_called()


@pytest.mark.parametrize("state", [Failed(), Crashed(), Cancelled()])
def test_unsuccessful_terminal_states_raise_with_safe_context(
    state: State,
    launch: Mock,
) -> None:
    state.message = "sensitive backend data"
    launch.return_value = FlowRun(flow_id=uuid4(), id=uuid4(), state=state)
    with pytest.raises(RuntimeError) as captured:
        prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    assert str(launch.return_value.id) in str(captured.value)
    assert state.type.value in str(captured.value)
    assert "sensitive backend data" not in str(captured.value)


@pytest.mark.parametrize("state", [Running(), None])
def test_nonfinal_or_missing_state_is_not_success(
    state: State | None, launch: Mock
) -> None:
    launch.return_value = FlowRun(flow_id=uuid4(), id=uuid4(), state=state)
    with pytest.raises(RuntimeError, match="did not return a final outcome"):
        prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))


def test_api_failure_does_not_retry_or_expose_backend_details(launch: Mock) -> None:
    launch.side_effect = RuntimeError("sensitive request URL and credentials")
    with pytest.raises(RuntimeError) as captured:
        prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    assert "Check the server before retrying" in str(captured.value)
    assert "sensitive" not in str(captured.value)
    assert captured.value.__suppress_context__
    launch.assert_called_once()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT quackframe.prefect_run_deployment(deployment_id := NULL)",
        "SELECT quackframe.prefect_run_deployment(deployment_entrypoint := NULL)",
    ],
)
def test_sql_null_never_silently_skips_the_call(sql: str, launch: Mock) -> None:
    with duckdb.connect() as connection:
        install_functions(connection, ("prefect_run_deployment",))
        with pytest.raises(duckdb.InvalidInputException):
            connection.execute(sql)
    launch.assert_not_called()


def test_sql_result_logging_does_not_launch_twice(tmp_path: Path, launch: Mock) -> None:
    script = tmp_path / "refresh.sql"
    script.write_text(
        "SELECT quackframe.prefect_run_deployment("
        f"deployment_id := '{DEPLOYMENT_ID}');",
        encoding="utf-8",
    )
    run(
        [script],
        config=QuackframeConfig(
            root=tmp_path,
            log_setting="all",
            functions=FunctionsConfig(enabled=("prefect_run_deployment",)),
        ),
    )
    launch.assert_called_once()


def test_deployment_failure_stops_statements_and_later_files(
    tmp_path: Path,
    launch: Mock,
) -> None:
    launch.return_value = FlowRun(flow_id=uuid4(), id=uuid4(), state=Failed())
    first = tmp_path / "first.sql"
    first.write_text(
        "SELECT quackframe.prefect_run_deployment("
        f"deployment_id := '{DEPLOYMENT_ID}');\n"
        "CREATE TABLE should_not_exist(value INTEGER);",
        encoding="utf-8",
    )
    later = tmp_path / "later.sql"
    later.write_text("CREATE TABLE later_file(value INTEGER);", encoding="utf-8")
    database = tmp_path / "state.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": tmp_path,
            "database": {"mode": "persistent", "path": database},
            "functions": {"enabled": ["prefect_run_deployment"]},
        }
    )
    with pytest.raises(ExecutionError) as captured:
        run([first, later], config=config)
    assert captured.value.sql_file == first
    assert captured.value.statement_number == 1
    with duckdb.connect(str(database)) as connection:
        assert connection.execute("SHOW TABLES").fetchall() == []


def test_cli_deployment_failure_exits_nonzero(tmp_path: Path, launch: Mock) -> None:
    launch.return_value = FlowRun(flow_id=uuid4(), id=uuid4(), state=Failed())
    (tmp_path / "pyproject.toml").write_text(
        '[tool.quackframe.functions]\nenabled = ["prefect_run_deployment"]\n',
        encoding="utf-8",
    )
    (tmp_path / "refresh.sql").write_text(
        "SELECT quackframe.prefect_run_deployment("
        f"deployment_id := '{DEPLOYMENT_ID}');",
        encoding="utf-8",
    )
    assert main(["run", "--root", str(tmp_path), "refresh.sql"]) == 1


def test_safe_run_context_reaches_prefect_logs(launch: Mock) -> None:
    launch.return_value = FlowRun(
        flow_id=uuid4(), id=uuid4(), state=Failed(message="sensitive data")
    )
    logger = Mock()
    with (
        patch("prefect.get_run_logger", return_value=logger),
        pytest.raises(RuntimeError),
    ):
        prefect_run_deployment(deployment_id=str(DEPLOYMENT_ID))
    message = logger.error.call_args.args[1]
    assert str(DEPLOYMENT_ID) in message
    assert str(launch.return_value.id) in message
    assert "FAILED" in message
    assert "sensitive" not in message


@pytest.mark.parametrize(
    "entrypoint", ["members-refresh/prod", "member refresh/daily run"]
)
def test_entrypoint_uses_prefect_native_name_lookup(
    entrypoint: str, launch: Mock
) -> None:
    result = prefect_run_deployment(
        deployment_entrypoint=entrypoint,
    )
    assert result == str(launch.return_value.id)
    assert launch.call_args.kwargs["name"] == entrypoint


@pytest.mark.parametrize(
    "entrypoint", ["", "prod", "/prod", "flow/", " /prod", "flow/ ", "flow/prod/extra"]
)
def test_invalid_entrypoints_do_not_launch(entrypoint: str, launch: Mock) -> None:
    with pytest.raises(ValueError, match="must have the form"):
        prefect_run_deployment(deployment_entrypoint=entrypoint)
    launch.assert_not_called()


@pytest.mark.parametrize(
    "identifier, entrypoint",
    [(None, None), (str(DEPLOYMENT_ID), "flow/prod"), ("", "flow/prod")],
)
def test_exactly_one_selector_is_required(
    identifier: str | None,
    entrypoint: str | None,
    launch: Mock,
) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        prefect_run_deployment(
            deployment_id=identifier,
            deployment_entrypoint=entrypoint,
        )
    launch.assert_not_called()


@pytest.mark.parametrize(
    "selector",
    [
        f"deployment_id := '{DEPLOYMENT_ID}'",
        "deployment_entrypoint := 'members-refresh/prod'",
    ],
)
def test_named_sql_options_launch_the_selected_deployment(
    selector: str, launch: Mock
) -> None:
    with duckdb.connect() as connection:
        install_functions(connection, ("prefect_run_deployment",))
        result = connection.execute(
            f"SELECT quackframe.prefect_run_deployment({selector})"
        ).fetchone()
    assert result == (str(launch.return_value.id),)
    expected = (
        DEPLOYMENT_ID
        if selector.startswith("deployment_id")
        else "members-refresh/prod"
    )
    assert launch.call_args.kwargs["name"] == expected
    launch.assert_called_once()


@pytest.mark.parametrize(
    "options",
    [
        "",
        f"deployment_id := '{DEPLOYMENT_ID}', deployment_entrypoint := 'flow/prod'",
        "deployment_entrypoint := NULL",
    ],
)
def test_sql_missing_or_conflicting_options_fail_before_launch(
    options: str, launch: Mock
) -> None:
    with duckdb.connect() as connection:
        install_functions(connection, ("prefect_run_deployment",))
        with pytest.raises(duckdb.InvalidInputException):
            connection.execute(f"SELECT quackframe.prefect_run_deployment({options})")
    launch.assert_not_called()


@pytest.mark.parametrize("api_error", [False, True])
def test_entrypoint_diagnostics_do_not_echo_caller_input(
    api_error: bool, launch: Mock
) -> None:
    marker = "private-flow/private-deployment"
    launch.return_value = FlowRun(
        flow_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        state=Failed(message="private state"),
    )
    if api_error:
        launch.side_effect = RuntimeError("private API details")
    logger = Mock()
    with (
        patch("prefect.get_run_logger", return_value=logger),
        pytest.raises(RuntimeError) as captured,
    ):
        prefect_run_deployment(deployment_entrypoint=marker)
    output = str(captured.value) + str(logger.error.call_args)
    assert "private" not in output
    if not api_error:
        assert str(DEPLOYMENT_ID) in output
        assert str(launch.return_value.id) in output


def test_sql_has_no_completion_timeout_option(launch: Mock) -> None:
    with duckdb.connect() as connection:
        install_functions(connection, ("prefect_run_deployment",))
        with pytest.raises(duckdb.BinderException):
            connection.execute(
                "SELECT quackframe.prefect_run_deployment("
                "deployment_entrypoint := 'flow/prod', timeout_seconds := 30)"
            )
    launch.assert_not_called()
