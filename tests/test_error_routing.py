"""Normal direct and external error disclosure through the runtime boundary."""

import traceback
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from duckdb import DuckDBPyConnection

from quackframe import ExecutionError, QuackframeConfig, run
from quackframe.engine import execute_plan
from quackframe.models import ExecutionResult, SqlFileResult
from quackframe.runtimes import registry
from quackframe.sql import PreparedSqlFile


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("allow", [False, True])
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT CAST('private-row' AS INTEGER)",
        "SELECT error('private-row')",
        "SELECT 'private-row' + FROM missing",
    ],
)
def test_error_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    external: bool,
    allow: bool,
    sql: str,
) -> None:
    # Use the real capability boundary without starting an external service.
    runtime = replace(registry.RUNTIME_REGISTRY[0], result_logging_is_external=external)
    monkeypatch.setattr(registry, "RUNTIME_REGISTRY", (runtime,))
    path = tmp_path / "failure.sql"
    path.write_text(sql, encoding="utf-8")
    with pytest.raises(ExecutionError) as captured:
        run(
            [path],
            config=QuackframeConfig(
                root=tmp_path,
                log_setting="none",
                allow_external_result_logging=allow,
            ),
        )
    rendered = "".join(traceback.format_exception(captured.value))
    if "FROM missing" in sql:
        assert ('syntax error at or near "FROM"' in rendered) == (not external or allow)
    else:
        assert ("private-row" in rendered) == (not external or allow)
    assert captured.value.sql_file == path
    assert captured.value.statement_number == 1
    if "error(" not in sql:
        assert captured.value.line == 1
        assert captured.value.column is not None


@pytest.mark.parametrize("allow", [False, True])
def test_prefect_task_receives_selected_error_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow: bool,
) -> None:
    pytest.importorskip("prefect")
    from quackframe.integrations.prefect import runtime as prefect_runtime

    logger = Mock()
    rendered_errors: list[str] = []
    monkeypatch.setattr(prefect_runtime, "get_run_logger", lambda: logger)

    def offline_runtime(
        sql_files: tuple[PreparedSqlFile, ...], config: QuackframeConfig
    ) -> ExecutionResult:
        def task(
            connection: DuckDBPyConnection, sql_file: PreparedSqlFile
        ) -> SqlFileResult:
            try:
                return prefect_runtime.execute_sql_file_task.fn(connection, sql_file)
            except ExecutionError as error:
                rendered_errors.append("".join(traceback.format_exception(error)))
                raise

        return execute_plan(sql_files, config, execute_file=task)

    def load_runtime(self: registry.RuntimeRegistration) -> registry.Runtime:
        return offline_runtime

    monkeypatch.setattr(registry.RuntimeRegistration, "load", load_runtime)
    path = tmp_path / "failure.sql"
    path.write_text("SELECT CAST('private-row' AS INTEGER)", encoding="utf-8")
    with pytest.raises(ExecutionError):
        run(
            [path],
            config=QuackframeConfig(
                root=tmp_path,
                runtime="prefect",
                log_setting="none",
                allow_external_result_logging=allow,
            ),
        )
    assert len(rendered_errors) == 1
    assert ("private-row" in rendered_errors[0]) == allow
    assert "Conversion" in rendered_errors[0]
    logger.info.assert_not_called()


@pytest.mark.parametrize("allow", [False, True])
def test_prefect_flow_selects_details_before_framework_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, allow: bool
) -> None:
    pytest.importorskip("prefect")
    from quackframe.errors import QuackframeError
    from quackframe.integrations.prefect import runtime as prefect_runtime

    monkeypatch.setattr(
        prefect_runtime, "execute_plan", Mock(side_effect=RuntimeError("private-setup"))
    )
    with pytest.raises(QuackframeError) as captured:
        prefect_runtime.execute_plan_flow.fn(
            (),
            QuackframeConfig(
                root=tmp_path,
                runtime="prefect",
                allow_external_result_logging=allow,
            ),
        )
    rendered = "".join(traceback.format_exception(captured.value))
    assert ("private-setup" in rendered) == allow


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("allow", [False, True])
def test_connection_errors_follow_runtime_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, external: bool, allow: bool
) -> None:
    import duckdb

    from quackframe import ConfigurationError, database

    runtime = replace(registry.RUNTIME_REGISTRY[0], result_logging_is_external=external)
    monkeypatch.setattr(registry, "RUNTIME_REGISTRY", (runtime,))
    monkeypatch.setattr(
        database.duckdb, "connect", Mock(side_effect=duckdb.IOException("private-path"))
    )
    path = tmp_path / "query.sql"
    path.write_text("SELECT 1", encoding="utf-8")
    with pytest.raises(ConfigurationError) as captured:
        run(
            [path],
            config=QuackframeConfig(
                root=tmp_path,
                log_setting="none",
                allow_external_result_logging=allow,
            ),
        )
    rendered = "".join(traceback.format_exception(captured.value))
    assert ("private-path" in rendered) == (not external or allow)
