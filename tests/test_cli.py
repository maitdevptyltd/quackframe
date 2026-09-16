"""Command-line behaviour tests."""

from pathlib import Path

import pytest

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
