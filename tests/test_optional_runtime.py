"""Keep core execution available when Prefect cannot be imported."""

import subprocess
import sys
from pathlib import Path


def test_core_and_optional_import_error_without_prefect(tmp_path: Path) -> None:
    (tmp_path / "example.sql").write_text("SELECT 1;", encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys

class NoPrefect(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "prefect" or fullname.startswith("prefect."):
            raise ModuleNotFoundError("Prefect is unavailable", name=fullname)

sys.meta_path.insert(0, NoPrefect())
from quackframe import OptionalDependencyError, QuackframeConfig, run

result = run(["example.sql"], config=QuackframeConfig())
assert result.statement_count == 1
assert not any(name == "prefect" or name.startswith("prefect.") for name in sys.modules)
try:
    from quackframe.integrations.prefect import quackframe_flow
except OptionalDependencyError as error:
    assert "quackframe[prefect]" in str(error)
else:
    raise AssertionError("The explicit optional import should fail")
""",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
