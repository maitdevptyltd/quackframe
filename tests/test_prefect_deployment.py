"""Public flow inputs and native Prefect deployment execution."""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import duckdb
import pytest

pytest.importorskip("prefect")

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterId
from prefect.exceptions import ParameterTypeError
from prefect.settings import PREFECT_API_URL
from prefect.testing.utilities import prefect_test_harness
from prefect.types.entrypoint import EntrypointType

from quackframe import (
    ConfigurationError,
    DatabaseConfig,
    ExecutionError,
    QuackframeConfig,
)
from quackframe.integrations.prefect import quackframe_flow


@pytest.fixture(scope="module")
def prefect_server() -> Iterator[None]:
    with prefect_test_harness():
        yield


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "deployment-example"\n'
        '[tool.quackframe]\nruntime = "direct"\n'
        "[tool.quackframe.functions]\nenabled = []\n",
        encoding="utf-8",
    )
    (root / "z-create.sql").write_text(
        "CREATE TEMP TABLE state(value INTEGER); INSERT INTO state VALUES (42);",
        encoding="utf-8",
    )
    (root / "a-use.sql").write_text(
        "CREATE TABLE output AS SELECT * FROM state;", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUACKFRAME_ROOT", str(root))
    return root


def test_flow_parameter_schema_and_config_round_trip(tmp_path: Path) -> None:
    schema = json.loads(quackframe_flow.parameters.model_dump_json())
    assert schema["required"] == ["sql_files"]
    assert set(schema["properties"]) == {"sql_files", "config_path", "config"}
    with pytest.raises(ParameterTypeError):
        quackframe_flow.validate_parameters({})

    config = QuackframeConfig(root=tmp_path, runtime="prefect")
    parameters = json.loads(
        json.dumps({"sql_files": ["a.sql"], "config": config.model_dump(mode="json")})
    )
    validated = quackframe_flow.validate_parameters(parameters)
    assert validated["config"] == config


@pytest.mark.usefixtures("prefect_server")
def test_public_flow_loads_worker_environment_and_names_run(project: Path) -> None:
    state = quackframe_flow(["z-create.sql", "a-use.sql"], return_state=True)
    result = state.result()
    assert result.runtime == "prefect"
    assert [item.path for item in result.files] == [
        project / "z-create.sql",
        project / "a-use.sql",
    ]
    with get_client(sync_client=True) as client:
        flow_run_id = state.state_details.flow_run_id
        assert flow_run_id is not None
        flow_run = client.read_flow_run(flow_run_id)
    assert flow_run.name == "deployment-example"
    assert flow_run.parent_task_run_id is None


@pytest.mark.usefixtures("prefect_server")
def test_explicit_native_run_name_takes_precedence(project: Path) -> None:
    state = quackframe_flow.with_options(flow_run_name="explicit-name")(
        ["z-create.sql"], return_state=True
    )
    with get_client(sync_client=True) as client:
        flow_run_id = state.state_details.flow_run_id
        assert flow_run_id is not None
        assert client.read_flow_run(flow_run_id).name == "explicit-name"


def test_alternate_config_keeps_environment_precedence(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alternate = project / "alternate.toml"
    alternate.write_text(
        '[tool.quackframe.database]\nmode = "persistent"\npath = "ignored.duckdb"\n',
        encoding="utf-8",
    )
    (project / ".env").write_text("QUACKFRAME_DATABASE_MODE=memory\n", encoding="utf-8")
    monkeypatch.setenv("QUACKFRAME_DATABASE_MODE", "temporary")
    with patch("quackframe.integrations.prefect.runtime.execute_plan") as execute:
        quackframe_flow.fn(["z-create.sql"], config_path=str(alternate))
    config = execute.call_args.args[1]
    assert config.runtime == "prefect"
    assert config.database.mode == "temporary"
    assert config.database.path is None


def test_config_object_bypasses_project_and_environment(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUACKFRAME_ROOT", str(project / "wrong-root"))
    monkeypatch.setenv("QUACKFRAME_DATABASE_MODE", "invalid")
    (project / "pyproject.toml").write_text("invalid TOML =", encoding="utf-8")
    config = QuackframeConfig(root=project, runtime="prefect")
    with patch("quackframe.integrations.prefect.runtime.execute_plan") as execute:
        quackframe_flow.fn(["z-create.sql"], config=config)
    assert execute.call_args.args[1] is config


def test_working_directory_fallback(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("QUACKFRAME_ROOT")
    monkeypatch.chdir(project)
    with patch("quackframe.integrations.prefect.runtime.execute_plan") as execute:
        quackframe_flow.fn(["z-create.sql"])
    assert execute.call_args.args[1].root == project


def test_conflicting_configuration_is_rejected(project: Path) -> None:
    config = QuackframeConfig(root=project, runtime="prefect")
    with pytest.raises(ConfigurationError, match="either config or config_path"):
        quackframe_flow.fn(["z-create.sql"], config=config, config_path="other.toml")
    with pytest.raises(ConfigurationError, match=r"config\.runtime"):
        quackframe_flow.fn(["z-create.sql"], config=QuackframeConfig(root=project))


@pytest.mark.parametrize("paths", [[], ["missing.sql"], ["z-create.sql", "bad.sql"]])
def test_invalid_inputs_fail_before_opening_database(
    project: Path, paths: list[str]
) -> None:
    (project / "bad.sql").write_text("SELECT FROM;", encoding="utf-8")
    config = QuackframeConfig(
        root=project,
        runtime="prefect",
        database=DatabaseConfig(mode="persistent", path=project / "not-created.duckdb"),
    )
    with pytest.raises((ConfigurationError, ExecutionError)):
        quackframe_flow.fn(paths, config=config)
    assert not (project / "not-created.duckdb").exists()


@pytest.mark.usefixtures("prefect_server")
def test_failure_stops_later_files_and_cleans_up(project: Path) -> None:
    (project / "fail.sql").write_text("SELECT * FROM missing_table;", encoding="utf-8")
    config = QuackframeConfig(
        root=project,
        runtime="prefect",
        database=DatabaseConfig(mode="temporary", path=project / "temporary.duckdb"),
    )
    with pytest.raises(ExecutionError) as captured:
        quackframe_flow(["z-create.sql", "fail.sql", "a-use.sql"], config=config)
    assert captured.value.sql_file == project / "fail.sql"
    assert not (project / "temporary.duckdb").exists()


def test_external_result_permission_checked_before_execution(project: Path) -> None:
    config = QuackframeConfig(root=project, runtime="prefect", log_setting="all")
    with (
        patch("quackframe.integrations.prefect.runtime.execute_plan") as execute,
        pytest.raises(ConfigurationError, match="External result logging"),
    ):
        quackframe_flow.fn(["z-create.sql"], config=config)
    execute.assert_not_called()


@pytest.mark.usefixtures("prefect_server")
def test_native_deployment_loads_installed_flow_in_a_fresh_process(
    project: Path, tmp_path: Path
) -> None:
    with get_client(sync_client=True) as client:
        client.create_work_pool(
            WorkPoolCreate(
                name="quackframe-test-pool",
                type="docker",
                base_job_template={
                    "job_configuration": {"image": "{{ image }}"},
                    "variables": {
                        "type": "object",
                        "properties": {"image": {"type": "string"}},
                    },
                },
            )
        )

    parameters = {"sql_files": ["z-create.sql", "a-use.sql"]}
    deployment_id = quackframe_flow.deploy(
        name="deployment-example",
        work_pool_name="quackframe-test-pool",
        image="example.invalid/reporting:test",
        build=False,
        push=False,
        entrypoint_type=EntrypointType.MODULE_PATH,
        parameters=parameters,
        print_next_steps=False,
    )
    assert isinstance(deployment_id, UUID)
    with get_client(sync_client=True) as client:
        deployment = client.read_deployment(deployment_id)
        assert deployment.entrypoint == (
            "quackframe.integrations.prefect.runtime.quackframe_flow"
        )
        assert deployment.parameters == parameters
        flow_run = client.create_flow_run_from_deployment(deployment_id)

    # The fresh worker process receives its own environment and filesystem.
    # No image is pulled: this exercises native deployment loading locally.
    worker_environment = {
        **os.environ,
        "PREFECT_API_URL": str(PREFECT_API_URL.value()),
        "PREFECT_API_KEY": "",
        "QUACKFRAME_ROOT": str(project),
        "QUACKFRAME_DATABASE_MODE": "persistent",
        "QUACKFRAME_DATABASE_PATH": str(project / "output.duckdb"),
    }
    worker_environment.pop("PYTHONPATH", None)
    process = subprocess.run(
        [sys.executable, "-m", "prefect.engine", str(flow_run.id)],
        cwd=tmp_path,
        env=worker_environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    with get_client(sync_client=True) as client:
        completed = client.read_flow_run(flow_run.id)
        tasks = client.read_task_runs(
            flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[flow_run.id]))
        )
        runs = client.read_flow_runs()
    assert completed.state is not None and completed.state.is_completed()
    assert completed.name == "deployment-example"
    assert len(tasks) == 2
    assert {task.name.rsplit("-", 1)[0] for task in tasks} == {"z-create", "a-use"}
    task_ids = {task.id for task in tasks}
    assert not any(run.parent_task_run_id in task_ids for run in runs)
    with duckdb.connect(str(project / "output.duckdb")) as connection:
        assert connection.execute("SELECT * FROM output").fetchall() == [(42,)]
