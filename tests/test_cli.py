"""Command-line behaviour tests."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from quackframe import QuackframeConfig, cli
from quackframe.cli import main


def test_cli_reports_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = tmp_path / "example.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    exit_code = main(["run", "--root", str(tmp_path), str(sql_file)])

    assert exit_code == 0
    assert "Completed 1 SQL file(s), 1 statement(s)" in capsys.readouterr().out


def test_cli_uses_nonzero_status_for_sql_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_file = tmp_path / "failure.sql"
    sql_file.write_text("SELECT * FROM missing_table;", encoding="utf-8")

    exit_code = main(["run", "--root", str(tmp_path), str(sql_file)])

    assert exit_code == 1
    assert "SQL execution failed" in capsys.readouterr().err


def test_cli_uses_distinct_status_for_configuration_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["run", "--root", str(tmp_path), "missing.sql"])

    assert exit_code == 2
    assert "Configuration error" in capsys.readouterr().err


def test_cli_runtime_choices_use_the_runtime_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "runtime_names", lambda: ("example",))

    arguments = cli.build_parser().parse_args(
        ["run", "--runtime", "example", "example.sql"]
    )

    assert arguments.runtime == "example"


@pytest.mark.parametrize(
    "flag, expected",
    [
        ("--allow-external-result-logging", True),
        ("--deny-external-result-logging", False),
    ],
)
def test_cli_external_logging_flags_override_in_both_directions(
    flag: str,
    expected: bool,
) -> None:
    arguments = cli.build_parser().parse_args(["run", flag, "example.sql"])

    assert arguments.allow_external_result_logging is expected


def test_cli_logging_overrides_default_to_unspecified() -> None:
    arguments = cli.build_parser().parse_args(["run", "example.sql"])

    assert arguments.log_setting is None
    assert arguments.allow_external_result_logging is None


def test_cli_passes_logging_overrides_to_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_config = Mock(return_value=QuackframeConfig())
    run = Mock(
        return_value=Mock(
            files=(),
            statement_count=0,
            runtime="direct",
        )
    )
    monkeypatch.setattr(cli, "load_config", load_config)
    monkeypatch.setattr(cli, "run", run)

    exit_code = main(
        [
            "run",
            "--log-setting",
            "none",
            "--deny-external-result-logging",
            "example.sql",
        ]
    )

    assert exit_code == 0
    assert load_config.call_args.kwargs["log_setting"] == "none"
    assert load_config.call_args.kwargs["allow_external_result_logging"] is False
