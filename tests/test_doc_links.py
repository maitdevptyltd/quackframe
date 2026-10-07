from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = (
    Path(__file__).resolve().parents[1]
    / ".agents/skills/quackframe-documentation/scripts/check_doc_links.py"
)


@pytest.mark.parametrize(
    ("heading", "fragment", "expected_status"),
    [
        ("register_secret", "register_secret", 0),
        ("`register_secret`", "register_secret", 0),
        ("`register_secret`", "registersecret", 1),
        ("Azure `connection_string`", "azure-connection_string", 0),
        ("`register_secret`", "register_secret-1", 0),
    ],
)
def test_checker_validates_github_identifier_anchors(
    tmp_path: Path, heading: str, fragment: str, expected_status: int
) -> None:
    (tmp_path / "README.md").write_text(
        f"[Function](functions.md#{fragment})\n", encoding="utf-8"
    )
    (tmp_path / "functions.md").write_text(
        f"# Functions\n\n## {heading}\n\n## {heading}\n", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_status, result.stdout + result.stderr
    if expected_status:
        assert f"functions.md#{fragment}" in result.stdout
    else:
        assert "All local Markdown link targets and anchors exist." in result.stdout
