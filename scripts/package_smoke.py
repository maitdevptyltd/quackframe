"""Install a built wheel into a clean Poetry project and exercise public entrypoints."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SMOKE = """
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
from quackframe import ExecutionError, QuackframeConfig, run
assert find_spec("prefect") is None
assert version("quackframe") == EXPECTED
config = QuackframeConfig(root=Path.cwd())
result = run(["first.sql", "second.sql"], config=config)
assert result.statement_count == 2
try:
    run(["first.sql", "bad.sql", "later.sql"], config=config)
except ExecutionError as error:
    assert error.sql_file.name == "bad.sql"
else:
    raise AssertionError("Expected fail-fast execution")
assert not Path("should-not-exist.csv").exists()
"""


def smoke(wheel: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="quackframe-package-") as directory:
        root = Path(directory)
        environment = os.environ.copy()
        # Do not let Poetry reuse the checkout's active virtual environment.
        environment.pop("VIRTUAL_ENV", None)
        environment.pop("PYTHONPATH", None)
        environment["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"
        # Poetry resolves local dependencies relative to the consumer project;
        # copying also avoids Windows cross-drive relative-path failures.
        installed_wheel = root / wheel.name
        shutil.copy2(wheel, installed_wheel)
        dependency = json.dumps(f"quackframe=={version}")
        (root / "pyproject.toml").write_text(
            '[project]\nname = "quackframe-package-smoke"\nversion = "0.0.0"\n'
            'requires-python = ">=3.11,<3.15"\n'
            f"dependencies = [{dependency}]\n"
            "[tool.poetry.dependencies]\n"
            f"quackframe = {{path = {json.dumps(installed_wheel.name)}}}\n",
            encoding="utf-8",
        )
        for name, sql in {
            "first.sql": "CREATE TEMP TABLE shared(value INTEGER);",
            "second.sql": "INSERT INTO shared VALUES (1);",
            "bad.sql": "SELECT * FROM missing_table;",
            "later.sql": "COPY (SELECT 1) TO 'should-not-exist.csv' (FORMAT CSV);",
        }.items():
            (root / name).write_text(sql, encoding="utf-8")
        (root / "smoke.py").write_text(
            f"EXPECTED = {version!r}\n" + SMOKE, encoding="utf-8"
        )
        for arguments in [
            ["install", "--no-root", "--no-interaction"],
            ["run", "python", "smoke.py"],
            ["run", "quackframe", "run", "first.sql", "second.sql"],
        ]:
            subprocess.run(
                ["poetry", *arguments], cwd=root, env=environment, check=True
            )
        failed = subprocess.run(
            ["poetry", "run", "quackframe", "run", "first.sql", "bad.sql", "later.sql"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        if failed.returncode == 0 or (root / "should-not-exist.csv").exists():
            raise AssertionError("CLI must fail before running the later SQL file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("version")
    arguments = parser.parse_args()
    smoke(arguments.wheel, arguments.version)
