"""Offline SQL Agent orchestration and DuckDB 2 transport regressions."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.mssql_run_job import function
from quackframe.sql_functions.mssql_run_job.client import AgentClient
from quackframe.sql_functions.mssql_run_job.models import (
    History,
    Job,
    JobResult,
    Outcome,
    Step,
)

JOB_ID = "12345678-1234-1234-1234-123456789abc"
JOB = Job(JOB_ID, "Nightly refresh", 4, 100)
STEPS = (Step(1, "Load", "TSQL"), Step(2, "Publish", "TSQL"))


def history(identifier: int, step: int, outcome: Outcome) -> History:
    return History(
        identifier,
        step,
        f"Step {step}",
        outcome,
        datetime(2026, 11, 23),
        12,
        50000,
        16,
        "Synthetic diagnostic",
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    fake = Mock()
    fake.resolve.return_value = JOB
    fake.steps.return_value = STEPS
    fake.history.return_value = (
        history(101, 1, Outcome.SUCCEEDED),
        history(102, 2, Outcome.SUCCEEDED),
        history(103, 0, Outcome.SUCCEEDED),
    )
    monkeypatch.setattr(function, "AgentClient", Mock(return_value=fake))
    monkeypatch.setattr(function, "sleep", Mock())
    return fake


def test_sql_macro_runs_once_on_duplicate_and_preserves_root(client: Mock) -> None:
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        install_functions(connection, ("mssql_run_job",), resources)
        connection.execute(
            "EXPLAIN SELECT quackframe.mssql_run_job("
            "database := 'server', job_name := 'job')"
        ).fetchall()
        client.start.assert_not_called()
        row = connection.execute(
            "SELECT quackframe.mssql_run_job(database := 'server', job_id := ?)",
            [JOB_ID],
        ).fetchone()
        assert row is not None
        report = json.loads(row[0])
        assert report["status"] == "succeeded"
        assert [step["status"] for step in report["attempts"]] == ["succeeded"] * 3
        client.start.assert_called_once_with(JOB)
        assert connection.execute("SELECT 42").fetchone() == (42,)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"job_id": JOB_ID, "job_name": "name"},
        {"job_id": "not a UUID"},
        {"job_name": " "},
        {"job_id": JOB_ID, "timeout_seconds": 0},
        {"job_id": JOB_ID, "timeout_seconds": float("inf")},
        {"job_id": JOB_ID, "poll_interval_seconds": 0},
        {"job_id": JOB_ID, "poll_interval_seconds": float("nan")},
    ],
)
def test_invalid_arguments_do_not_start(
    client: Mock, arguments: dict[str, object]
) -> None:
    with duckdb.connect() as connection, pytest.raises(ValueError):
        function.mssql_run_job(SessionResources(connection), "server", **arguments)  # type: ignore[arg-type]
    client.start.assert_not_called()


def test_waits_and_stops_at_first_terminal_history(client: Mock) -> None:
    client.history.side_effect = [
        (history(101, 0, Outcome.RUNNING),),
        (
            history(102, 1, Outcome.SUCCEEDED),
            history(103, 0, Outcome.SUCCEEDED),
            history(104, 1, Outcome.FAILED),
        ),
    ]
    with duckdb.connect() as connection:
        report = json.loads(
            function.mssql_run_job(
                SessionResources(connection), "server", job_name="Nightly refresh"
            )
        )
    assert len(report["attempts"]) == 2
    assert report["steps_without_history"][0]["status"] == "not_recorded"
    client.start.assert_called_once()
    assert client.history.call_count == 2


@pytest.mark.parametrize("outcome", [Outcome.FAILED, Outcome.CANCELLED])
def test_failure_stops_later_sql(client: Mock, outcome: Outcome) -> None:
    client.history.return_value = (history(101, 1, outcome), history(102, 0, outcome))
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        install_functions(connection, ("mssql_run_job",), resources)
        with pytest.raises(duckdb.InvalidInputException, match="failed"):
            connection.execute(
                "SELECT quackframe.mssql_run_job("
                "database := 'server', job_name := 'job');"
                "CREATE TABLE should_not_run (id INT)"
            )
        assert connection.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'should_not_run'"
        ).fetchone() == (0,)


def test_failed_step_cannot_be_hidden_by_successful_job(client: Mock) -> None:
    client.history.return_value = (
        history(101, 1, Outcome.FAILED),
        history(102, 0, Outcome.SUCCEEDED),
    )
    with duckdb.connect() as connection, pytest.raises(RuntimeError, match="failed"):
        function.mssql_run_job(SessionResources(connection), "server", job_id=JOB_ID)


def test_native_retry_is_reported_without_resubmission(client: Mock) -> None:
    client.history.return_value = (
        history(101, 1, Outcome.RETRY),
        history(102, 1, Outcome.SUCCEEDED),
        history(103, 0, Outcome.SUCCEEDED),
    )
    with duckdb.connect() as connection:
        report = json.loads(
            function.mssql_run_job(
                SessionResources(connection), "server", job_id=JOB_ID
            )
        )
    assert report["attempts"][0]["status"] == "retry"
    client.start.assert_called_once()


@pytest.mark.parametrize("interval", [None, 2.0])
def test_no_timeout_waits_with_default_or_selected_poll_interval(
    client: Mock, monkeypatch: pytest.MonkeyPatch, interval: float | None
) -> None:
    completed = client.history.return_value
    client.history.side_effect = [(), (), completed]
    clock = Mock(side_effect=[0, 7200, 14400])
    sleeper = Mock()
    monkeypatch.setattr(function, "monotonic", clock)
    monkeypatch.setattr(function, "sleep", sleeper)
    with duckdb.connect() as connection:
        result = function.mssql_run_job(
            SessionResources(connection),
            "server",
            job_id=JOB_ID,
            poll_interval_seconds=interval,
        )
    assert json.loads(result)["status"] == "succeeded"
    assert [call.args for call in sleeper.call_args_list] == [(interval or 5.0,)] * 2
    clock.assert_not_called()
    client.start.assert_called_once()


def test_explicit_timeout_limits_poll_sleep(
    client: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.history.return_value = ()
    monkeypatch.setattr(function, "monotonic", Mock(side_effect=[0, 0, 1]))
    sleeper = Mock()
    monkeypatch.setattr(function, "sleep", sleeper)
    with duckdb.connect() as connection, pytest.raises(RuntimeError, match="timeout"):
        function.mssql_run_job(
            SessionResources(connection), "server", job_id=JOB_ID, timeout_seconds=1
        )
    sleeper.assert_called_once_with(1)
    client.start.assert_called_once()


def test_timeout_never_resubmits_or_stops_remote_job(
    client: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.history.return_value = ()
    monkeypatch.setattr(function, "monotonic", Mock(side_effect=[0, 10]))
    with (
        duckdb.connect() as connection,
        pytest.raises(RuntimeError, match="outcome unknown"),
    ):
        function.mssql_run_job(
            SessionResources(connection), "server", job_id=JOB_ID, timeout_seconds=1
        )
    client.start.assert_called_once()


def test_lost_start_response_is_not_retried(client: Mock) -> None:
    client.start.side_effect = OSError("Synthetic lost response")
    with (
        duckdb.connect() as connection,
        pytest.raises(RuntimeError, match="outcome unknown"),
    ):
        function.mssql_run_job(SessionResources(connection), "server", job_id=JOB_ID)
    client.start.assert_called_once()
    client.history.assert_not_called()


def test_detailed_step_reports_respect_external_policy(client: Mock) -> None:
    logger = Mock()
    with duckdb.connect() as connection:
        resources = SessionResources(
            connection, include_error_details=False, error_logger=logger
        )
        function.mssql_run_job(resources, "server", job_id=JOB_ID)
    assert logger.info.call_args.kwargs["extra"] == {"send_to_api": False}
    assert "Synthetic diagnostic" in logger.info.call_args.args[1]


def test_summary_without_step_evidence_is_not_success() -> None:
    result = JobResult(JOB, STEPS, (history(101, 0, Outcome.SUCCEEDED),))
    assert not result.succeeded


def test_start_transport_binds_values_and_preserves_procedure_parameter() -> None:
    connection = Mock()
    AgentClient(connection, "server'alias").start(JOB)
    query, arguments = connection.execute.call_args.args
    assert query == "SELECT mssql_exec_params(?, ?, ?)"
    database, sql, parameters = arguments
    assert database == "server'alias"
    assert "sp_start_job @job_id = @id" in sql
    assert "@requested_job_id" in sql
    assert JOB_ID not in sql
    assert parameters == {
        "requested_job_id": JOB_ID,
        "session_id": 4,
        "history_id": 100,
    }
    assert "history changed before submission" in sql
    connection.execute.return_value.fetchall.assert_called_once()


def test_attachment_validation_rejects_non_mssql() -> None:
    with (
        duckdb.connect() as connection,
        pytest.raises(ValueError, match="attached MSSQL"),
    ):
        AgentClient(connection, "memory").validate_attachment()


def test_public_runner_stops_before_later_file(client: Mock, tmp_path: Path) -> None:
    from quackframe import DatabaseConfig, ExecutionError, QuackframeConfig, run
    from quackframe.config import FunctionsConfig

    client.history.return_value = (
        history(101, 1, Outcome.FAILED),
        history(102, 0, Outcome.FAILED),
    )
    job_file = tmp_path / "job.sql"
    job_file.write_text(
        "SELECT quackframe.mssql_run_job(database := 'server', job_name := 'job');"
    )
    later = tmp_path / "later.sql"
    later.write_text("CREATE TABLE should_not_run (id INT);")
    database = tmp_path / "results.duckdb"
    config = QuackframeConfig(
        root=tmp_path,
        database=DatabaseConfig(mode="persistent", path=database),
        functions=FunctionsConfig(enabled=("mssql_run_job",)),
    )
    with pytest.raises(ExecutionError) as caught:
        run([job_file, later], config=config)
    assert caught.value.sql_file == job_file
    assert caught.value.statement_number == 1
    with duckdb.connect(str(database)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name='should_not_run'"
        ).fetchone() == (0,)


@pytest.mark.parametrize("status", [Outcome.FAILED, Outcome.CANCELLED])
def test_failed_summary_is_known_even_without_step_history(status: Outcome) -> None:
    assert JobResult(JOB, STEPS, (history(101, 0, status),)).status == "failed"


def test_bound_transport_works_inside_real_duckdb_udf() -> None:
    # A local macro stands in for the extension's bound STRUCT API. Real DuckDB
    # binds values through the duplicate while the root is executing a UDF.
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE MACRO mssql_scan_params(database, statement, params) "
            "AS TABLE SELECT database, statement, struct_extract(params, 'selector')"
        ).complete()

        def probe() -> str:
            with connection.duplicate() as duplicate:
                rows = AgentClient(duplicate, "server'alias").query(
                    "SELECT @selector", {"selector": "O'Brien @job_id"}
                )
                return json.dumps(rows[0])

        connection.create_function(  # pyright: ignore[reportUnknownMemberType]
            "transport_probe", probe, side_effects=True
        )
        assert connection.execute("SELECT transport_probe()").fetchall() == [
            (json.dumps(["server'alias", "SELECT @selector", "O'Brien @job_id"]),)
        ]
        assert connection.sql("SELECT 42").fetchall() == [(42,)]


def test_attachment_validation_consumes_result_before_relation_use() -> None:
    with duckdb.connect() as connection:
        with pytest.raises(ValueError, match="attached MSSQL"):
            AgentClient(connection, "memory").validate_attachment()
        assert connection.sql("SELECT 42").fetchall() == [(42,)]
