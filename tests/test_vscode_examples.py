import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("example", ["basic", "prefect"])
@pytest.mark.parametrize("fails", [False, True])
def test_example_launcher_forwards_output_and_exit_status(
    example: str, fails: bool, tmp_path: Path
) -> None:
    sql_file = tmp_path / "query with spaces.sql"
    sql_file.write_text(
        "SELECT * FROM missing_baseline_table;"
        if fails
        else "SELECT 'launcher smoke test' AS message;",
        encoding="utf-8",
    )
    launcher = REPOSITORY_ROOT / "examples" / example / ".vscode" / "run_quackframe.py"

    # Use the installed development environment without contacting an orchestrator
    # or creating a database, regardless of the caller's local configuration.
    result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--runtime",
            "direct",
            "--memory",
            "--log-setting",
            "all",
            str(sql_file),
        ],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    if fails:
        assert result.returncode != 0
        assert "missing_baseline_table" in result.stderr
        assert "Completed" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "launcher smoke test" in result.stdout
        summary = "Completed 1 SQL file(s), 1 statement(s), runtime=direct"
        assert summary in result.stdout
