"""Configuration precedence and path lifecycle tests."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from quackframe import ConfigurationError, QuackframeConfig, load_config, run


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


def test_direct_execution_works_when_prefect_cannot_be_imported(
    tmp_path: Path,
) -> None:
    sql_file = tmp_path / "direct.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    script = f"""
import importlib.abc
from pathlib import Path
import sys

class BlockPrefect(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "prefect" or fullname.startswith("prefect."):
            raise ImportError("Prefect is intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockPrefect())

from quackframe import QuackframeConfig, run

result = run(
    [Path({str(sql_file)!r})],
    config=QuackframeConfig(root=Path({str(tmp_path)!r})),
)
assert result.runtime == "direct"
"""

    completed = subprocess.run([sys.executable, "-c", script], check=False)

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


def test_explicit_values_override_environment_dotenv_and_toml(tmp_path: Path) -> None:
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
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\nQUACKFRAME_DATABASE_PATH="from-dotenv.duckdb"\n',
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


def test_quoted_dotenv_values_use_existing_environment_translation(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                'QUACKFRAME_RUNTIME="prefect"',
                'QUACKFRAME_LOG_SETTING="all"',
                'QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING="true"',
                'QUACKFRAME_DATABASE_MODE="persistent"',
                'QUACKFRAME_DATABASE_PATH="data/from dotenv.duckdb"',
                'DUCKDB_TEMP_DIRECTORY="scratch/from dotenv"',
            )
        ),
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, environ={})

    assert config.runtime == "prefect"
    assert config.log_setting == "all"
    assert config.allow_external_result_logging is True
    assert config.database.mode == "persistent"
    assert config.database.path == tmp_path / "data/from dotenv.duckdb"
    assert config.duckdb.settings == {
        "temp_directory": "scratch/from dotenv",
    }


@pytest.mark.parametrize("source", ["dotenv", "environment"])
def test_boolean_and_path_conversion_match_environment_behavior(
    tmp_path: Path,
    source: str,
) -> None:
    values = {
        "QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING": "true",
        "QUACKFRAME_DATABASE_PATH": "data/results.duckdb",
    }
    environment: dict[str, str] = {}
    if source == "dotenv":
        (tmp_path / ".env").write_text(
            "\n".join(f'{name}="{value}"' for name, value in values.items()),
            encoding="utf-8",
        )
    else:
        environment = values

    config = load_config(root=tmp_path, environ=environment)

    assert config.allow_external_result_logging is True
    assert config.database.mode == "persistent"
    assert config.database.path == tmp_path / "data/results.duckdb"


def test_environment_overrides_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\nQUACKFRAME_LOG_SETTING="all"\n',
        encoding="utf-8",
    )

    config = load_config(
        root=tmp_path,
        environ={
            "QUACKFRAME_RUNTIME": "direct",
            "QUACKFRAME_LOG_SETTING": "none",
        },
    )

    assert config.runtime == "direct"
    assert config.log_setting == "none"


@pytest.mark.parametrize(
    ("dotenv_values", "environment", "expected_mode", "expected_path"),
    [
        (
            {"QUACKFRAME_DATABASE_PATH": "from-dotenv.duckdb"},
            {"QUACKFRAME_DATABASE_MODE": "memory"},
            "memory",
            None,
        ),
        (
            {"QUACKFRAME_DATABASE_MODE": "memory"},
            {"QUACKFRAME_DATABASE_PATH": "from-environment.duckdb"},
            "persistent",
            "from-environment.duckdb",
        ),
    ],
)
def test_environment_database_fields_override_dotenv_as_one_source(
    tmp_path: Path,
    dotenv_values: dict[str, str],
    environment: dict[str, str],
    expected_mode: str,
    expected_path: str | None,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(f'{name}="{value}"' for name, value in dotenv_values.items()),
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, environ=environment)

    assert config.database.mode == expected_mode
    assert config.database.path == (
        tmp_path / expected_path if expected_path is not None else None
    )


def test_dotenv_overrides_allowed_toml_settings(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.quackframe]
runtime = "direct"

[tool.quackframe.database]
mode = "persistent"
path = "from-toml.duckdb"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\nQUACKFRAME_DATABASE_PATH="from-dotenv.duckdb"\n',
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, environ={})

    assert config.runtime == "prefect"
    assert config.database.path == tmp_path / "from-dotenv.duckdb"


def test_missing_dotenv_preserves_current_behavior(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, environ={})

    assert config == QuackframeConfig(root=tmp_path)


def test_parent_dotenv_is_not_searched(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\n',
        encoding="utf-8",
    )

    config = load_config(root=project_root, environ={})

    assert config.runtime == "direct"


def test_dotenv_root_does_not_relocate_runtime_root(tmp_path: Path) -> None:
    requested_root = tmp_path / "requested"
    other_root = tmp_path / "other"
    requested_root.mkdir()
    other_root.mkdir()
    (requested_root / ".env").write_text(
        f'QUACKFRAME_ROOT="{other_root}"\nQUACKFRAME_RUNTIME="prefect"\n',
        encoding="utf-8",
    )
    (other_root / ".env").write_text(
        'QUACKFRAME_LOG_SETTING="all"\n',
        encoding="utf-8",
    )

    config = load_config(
        environ={"QUACKFRAME_ROOT": str(requested_root)},
    )

    assert config.root == requested_root
    assert config.runtime == "prefect"
    assert config.log_setting == "annotations-only"


def test_dotenv_loading_does_not_mutate_process_environment(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\nUNRELATED_SECRET="not-exported"\n',
        encoding="utf-8",
    )
    original_environment = dict(os.environ)

    load_config(root=tmp_path, environ={})

    assert dict(os.environ) == original_environment


def test_dotenv_values_do_not_leak_between_projects(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\n',
        encoding="utf-8",
    )

    first_config = load_config(root=first_root, environ={})
    second_config = load_config(root=second_root, environ={})

    assert first_config.runtime == "prefect"
    assert second_config.runtime == "direct"


def test_resolved_config_bypasses_source_reloading(tmp_path: Path) -> None:
    sql_file = tmp_path / "direct.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="direct"\n',
        encoding="utf-8",
    )
    dotenv_parser = Mock(return_value={"QUACKFRAME_RUNTIME": "direct"})

    with patch("quackframe.config.dotenv_values", dotenv_parser):
        config = load_config(root=tmp_path, environ={})
        QuackframeConfig.model_validate(config.model_dump())
        run_result = run([sql_file], config=config)

    dotenv_parser.assert_called_once()
    assert run_result.runtime == "direct"


def test_unreadable_dotenv_is_a_safe_configuration_error(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text('UNRELATED_SECRET="sensitive"\n', encoding="utf-8")

    with (
        patch.object(Path, "open", side_effect=PermissionError("sensitive detail")),
        pytest.raises(ConfigurationError) as captured,
    ):
        load_config(root=tmp_path, environ={})

    assert str(dotenv_path) in str(captured.value)
    assert "sensitive" not in str(captured.value)


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
