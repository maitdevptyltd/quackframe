"""Configuration precedence and path lifecycle tests."""

import subprocess
import sys
from pathlib import Path

import pytest

from quackframe import ConfigurationError, QuackframeConfig, load_config


def test_base_package_does_not_import_prefect() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import quackframe; assert 'prefect' not in sys.modules",
        ],
        check=False,
    )

    assert completed.returncode == 0


def test_defaults_use_current_working_directory_and_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config(environ={})

    assert config.root == tmp_path
    assert config.runtime == "direct"
    assert config.database.mode == "memory"
    assert config.functions.enabled == ()


def test_explicit_values_override_environment_and_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.quackframe]
runtime = "prefect"

[tool.quackframe.database]
mode = "persistent"
path = "from-toml.duckdb"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(
        root=tmp_path,
        runtime="direct",
        database_mode="persistent",
        database_path="explicit.duckdb",
        environ={"QUACKFRAME_RUNTIME": "prefect"},
    )

    assert config.runtime == "direct"
    assert config.database.path == tmp_path / "explicit.duckdb"


def test_environment_overrides_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.quackframe]\nruntime = "direct"\n',
        encoding="utf-8",
    )

    config = load_config(
        root=tmp_path,
        environ={"QUACKFRAME_RUNTIME": "prefect"},
    )

    assert config.runtime == "prefect"


def test_memory_override_clears_a_toml_database_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.quackframe.database]
mode = "persistent"
path = "project.duckdb"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, database_mode="memory", environ={})

    assert config.database.mode == "memory"
    assert config.database.path is None


def test_persistent_database_requires_a_path() -> None:
    with pytest.raises(ConfigurationError, match=r"database\.path is required"):
        load_config(database_mode="persistent", environ={})


def test_unknown_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        QuackframeConfig.model_validate({"unknown": True})
