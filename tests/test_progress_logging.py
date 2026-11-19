"""Progress is ordered, safe and delivered by the selected runtime."""

import logging
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from quackframe import ExecutionError, QuackframeConfig, run
from quackframe import sql as sql_module


def test_direct_progress_follows_file_and_statement_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = tmp_path / "create.sql"
    first.write_text("CREATE TEMP TABLE state(value VARCHAR);", encoding="utf-8")
    second = tmp_path / "use.sql"
    second.write_text(
        "INSERT INTO state VALUES ('private-value'); SELECT * FROM state;",
        encoding="utf-8",
    )
    root_handlers = list(logging.getLogger().handlers)

    result = run(
        [first, second], config=QuackframeConfig(root=tmp_path, log_setting="none")
    )

    output = capsys.readouterr()
    messages = [
        re.sub(r" \(\d+\.\d{3}s\)$", "", line) for line in output.err.splitlines()
    ]
    assert messages == [
        f"File started: {first}",
        f"Statement 1 started: {first}",
        f"Statement 1 completed: {first}",
        f"File completed: {first}",
        f"File started: {second}",
        f"Statement 1 started: {second}",
        f"Statement 1 completed: {second}",
        f"Statement 2 started: {second}",
        f"Statement 2 completed: {second}",
        f"File completed: {second}",
    ]
    assert len(re.findall(r"\(\d+\.\d{3}s\)", output.err)) == 5
    assert output.out == ""
    assert "private-value" not in output.err
    assert "INSERT" not in output.err
    assert result.statement_count == 3
    assert logging.getLogger().handlers == root_handlers


def test_failure_progress_has_elapsed_time_and_stops_later_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failing = tmp_path / "failure.sql"
    failing.write_text(
        "SELECT 1; SELECT CAST('private-value' AS INTEGER); SELECT 3;",
        encoding="utf-8",
    )
    later = tmp_path / "later.sql"
    later.write_text("SELECT 4;", encoding="utf-8")
    monkeypatch.setattr(
        sql_module, "perf_counter", Mock(side_effect=[10.0, 10.1, 10.4, 10.5, 11.0])
    )

    with pytest.raises(ExecutionError) as captured:
        run(
            [failing, later], config=QuackframeConfig(root=tmp_path, log_setting="none")
        )

    assert capsys.readouterr().err.splitlines() == [
        f"File started: {failing}",
        f"Statement 1 started: {failing}",
        f"Statement 1 completed: {failing} (0.300s)",
        f"Statement 2 started: {failing}",
        f"Statement 2 failed: {failing} (0.500s)",
        f"File failed: {failing} (1.000s)",
    ]
    assert captured.value.statement_number == 2


def test_prefect_task_routes_progress_and_result_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("prefect")
    import duckdb

    from quackframe.integrations.prefect import runtime

    path = tmp_path / "selected.sql"
    path.write_text("-- quackframe: log-result\nSELECT 'visible';", encoding="utf-8")
    prepared = sql_module.prepare_sql_files(
        [path], root=tmp_path, log_setting="annotations-only"
    )[0]
    logger = Mock()
    monkeypatch.setattr(runtime, "get_run_logger", lambda: logger)

    with duckdb.connect() as connection:
        runtime.execute_sql_file_task.fn(connection, prepared)

    assert [call.args[0] for call in logger.info.call_args_list] == [
        "File started: %s",
        "Statement %d started: %s",
        "\n%s",
        "Statement %d completed: %s (%.3fs)",
        "File completed: %s (%.3fs)",
    ]
    assert "visible" in logger.info.call_args_list[2].args[1]
    logger.error.assert_not_called()
