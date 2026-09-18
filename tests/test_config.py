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
    assert config.log_setting == "annotations-only"
    assert config.allow_external_result_logging is False
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


def test_logging_environment_values_are_typed() -> None:
    config = load_config(
        environ={
            "QUACKFRAME_LOG_SETTING": "all",
            "QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING": "true",
        }
    )

    assert config.log_setting == "all"
    assert config.allow_external_result_logging is True


def test_explicit_logging_values_override_environment() -> None:
    config = load_config(
        log_setting="none",
        allow_external_result_logging=False,
        environ={
            "QUACKFRAME_LOG_SETTING": "all",
            "QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING": "true",
        },
    )

    assert config.log_setting == "none"
    assert config.allow_external_result_logging is False


@pytest.mark.parametrize(
    "setting, value",
    [
        ("log_setting", '"all"'),
        ("allow_external_result_logging", "true"),
    ],
)
def test_logging_controls_are_rejected_from_project_config(
    tmp_path: Path,
    setting: str,
    value: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.quackframe]\n{setting} = {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=f"{setting} is not allowed"):
        load_config(root=tmp_path, environ={})


def test_project_name_is_loaded_for_runtime_display(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "analytics-workflows"\n',
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, environ={})

    assert config.project_name == "analytics-workflows"


def test_runtime_validation_uses_the_runtime_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quackframe import config as config_module

    monkeypatch.setattr(config_module, "runtime_names", lambda: ("example",))

    config = QuackframeConfig(runtime="example")

    assert config.runtime == "example"


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
