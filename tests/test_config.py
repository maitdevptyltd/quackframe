"""Configuration precedence and path lifecycle tests."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from quackframe import ConfigurationError, QuackframeConfig, load_config, run
from quackframe.config import DatabaseConfig, DatabaseMode, DuckDBConfig


@pytest.mark.parametrize("source", ["model", "python", "toml"])
@pytest.mark.parametrize("path_kind", ["home", "relative", "absolute"])
def test_database_paths_expand_home_before_resolving_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, path_kind: str
) -> None:
    home = tmp_path / "home"
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr("quackframe.config._read_dotenv", Mock(return_value={}))
    paths = {
        "home": (Path("~/example.duckdb"), home / "example.duckdb"),
        "relative": (Path("data/example.duckdb"), root / "data/example.duckdb"),
        "absolute": (tmp_path / "example.duckdb", tmp_path / "example.duckdb"),
    }
    path, expected = paths[path_kind]

    if source == "model":
        config = QuackframeConfig(
            root=root, database=DatabaseConfig(mode="persistent", path=path)
        )
    elif source == "python":
        config = load_config(root=root, database_path=path, environ={})
    else:
        (root / "pyproject.toml").write_text(
            '[tool.quackframe.database]\nmode = "persistent"\n'
            f'path = "{path.as_posix()}"\n',
            encoding="utf-8",
        )
        config = load_config(root=root, environ={})

    assert config.database.mode == "persistent"
    assert config.database.path == expected
    assert not home.exists()


def test_temporary_database_rejects_home_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="cannot be used with temporary mode"):
        QuackframeConfig.model_validate(
            {"root": tmp_path, "database": {"mode": "temporary", "path": "~/a.duckdb"}}
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4, "4"),
        (0, "0"),
        (-2, "-2"),
        (0.5, "0.5"),
        (True, "true"),
        (False, "false"),
        ("4GB", "4GB"),
        ("", ""),
    ],
)
def test_duckdb_settings_normalize_scalars(value: object, expected: str) -> None:
    config = DuckDBConfig.model_validate({"settings": {"option": value}})

    assert config.settings == {"option": expected}


@pytest.mark.parametrize("value", [None, [], {}, [4], {"nested": 4}, object(), b"4"])
def test_duckdb_settings_reject_unsupported_values(value: object) -> None:
    with pytest.raises(ValidationError, match="DuckDB settings must be"):
        DuckDBConfig.model_validate({"settings": {"option": value}})


def test_duckdb_settings_from_toml_work_in_duckdb(tmp_path: Path) -> None:
    import duckdb

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.quackframe.duckdb.settings]
threads = 4
index_scan_percentage = 0.5
preserve_insertion_order = false
enable_object_cache = true
memory_limit = "1GB"
""",
        encoding="utf-8",
    )

    config = load_config(root=tmp_path, environ={})

    assert config.duckdb.settings == {
        "threads": "4",
        "index_scan_percentage": "0.5",
        "preserve_insertion_order": "false",
        "enable_object_cache": "true",
        "memory_limit": "1GB",
    }
    with duckdb.connect(":memory:", config={**config.duckdb.settings}) as connection:
        assert connection.execute(
            "SELECT current_setting('threads'), "
            "current_setting('index_scan_percentage'), "
            "current_setting('preserve_insertion_order'), "
            "current_setting('enable_object_cache')"
        ).fetchone() == (4, 0.5, False, True)


@pytest.mark.parametrize("value", ["[4]", "{nested = 4}", "2026-10-14"])
def test_duckdb_settings_reject_unsupported_toml(tmp_path: Path, value: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.quackframe.duckdb.settings]\nthreads = {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="DuckDB settings must be"):
        load_config(root=tmp_path, environ={})


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
    assert config.allow_external_error_logging is False
    assert config.database.mode == "memory"
    assert config.functions.enabled == ()


@pytest.mark.parametrize("root_source", ["explicit", "environment"])
@pytest.mark.parametrize("path_kind", ["string", "path", "absolute", "default"])
def test_configuration_paths_use_selected_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_source: str,
    path_kind: str,
) -> None:
    working_directory = tmp_path / "working"
    runtime_root = tmp_path / "runtime"
    external_directory = tmp_path / "external"
    for directory in (working_directory, runtime_root, external_directory):
        directory.mkdir()
        for filename in ("settings.toml", "pyproject.toml"):
            (directory / filename).write_text(
                f'[project]\nname = "{directory.name}"\n', encoding="utf-8"
            )
    monkeypatch.chdir(working_directory)

    config_path: str | Path | None = "settings.toml"
    if path_kind == "path":
        config_path = Path("settings.toml")
    elif path_kind == "absolute":
        config_path = external_directory / "settings.toml"
    elif path_kind == "default":
        config_path = None

    explicit_root = runtime_root if root_source == "explicit" else None
    environment_root = working_directory if explicit_root else runtime_root
    config = load_config(
        root=explicit_root,
        config_path=config_path,
        environ={"QUACKFRAME_ROOT": str(environment_root)},
    )

    assert config.root == runtime_root
    assert config.project_name == ("external" if path_kind == "absolute" else "runtime")


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


@pytest.mark.parametrize(
    "database_path", ["data/example.duckdb", Path("data/example.duckdb")]
)
def test_python_database_path_implies_persistent_mode(
    tmp_path: Path, database_path: str | Path
) -> None:
    config = load_config(root=tmp_path, database_path=database_path, environ={})

    assert config.database.mode == "persistent"
    assert config.database.path == tmp_path / "data/example.duckdb"


@pytest.mark.parametrize("source", ["toml", "dotenv", "environment"])
@pytest.mark.parametrize("inherited_mode", ["memory", "temporary", "persistent"])
def test_python_database_path_overrides_inherited_database_settings(
    tmp_path: Path, source: str, inherited_mode: str
) -> None:
    environment = {"QUACKFRAME_DATABASE_MODE": inherited_mode}
    if inherited_mode == "persistent":
        environment["QUACKFRAME_DATABASE_PATH"] = "inherited.duckdb"
    if source == "toml":
        settings = f'[tool.quackframe.database]\nmode = "{inherited_mode}"\n'
        if inherited_mode == "persistent":
            settings += 'path = "inherited.duckdb"\n'
        (tmp_path / "pyproject.toml").write_text(settings, encoding="utf-8")
    elif source == "dotenv":
        (tmp_path / ".env").write_text(
            "\n".join(f'{key}="{value}"' for key, value in environment.items()),
            encoding="utf-8",
        )

    config = load_config(
        root=tmp_path,
        database_path="data/example.duckdb",
        environ=environment if source == "environment" else {},
    )

    assert config.database.mode == "persistent"
    assert config.database.path == tmp_path / "data/example.duckdb"


@pytest.mark.parametrize("mode", ["memory", "temporary"])
def test_python_database_path_preserves_explicit_mode_validation(
    tmp_path: Path, mode: DatabaseMode
) -> None:
    with pytest.raises(ConfigurationError, match=f"cannot be used with {mode} mode"):
        load_config(
            root=tmp_path,
            database_mode=mode,
            database_path="data/example.duckdb",
            environ={},
        )


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
    assert config.allow_external_error_logging is False


@pytest.mark.parametrize(
    "setting, value",
    [
        ("log_setting", '"all"'),
        ("allow_external_result_logging", "true"),
        ("allow_external_error_logging", "true"),
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


@pytest.mark.parametrize("root_source", ["explicit", "environment", "cwd"])
@pytest.mark.parametrize(
    "setting, guidance",
    [
        ("root", "use an environment or invocation value"),
        ("project_name", "use [project].name"),
    ],
)
def test_root_and_project_name_are_rejected_from_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_source: str,
    setting: str,
    guidance: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "analytics-workflows"\n'
        f'[tool.quackframe]\n{setting} = "other"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as error:
        load_config(
            root=tmp_path if root_source == "explicit" else None,
            environ={"QUACKFRAME_ROOT": str(tmp_path)}
            if root_source == "environment"
            else {},
        )

    assert str(error.value) == (
        f"[tool.quackframe].{setting} is not allowed; {guidance}"
    )


def test_typed_config_accepts_root_and_project_name(tmp_path: Path) -> None:
    config = QuackframeConfig(root=tmp_path, project_name="analytics-workflows")

    assert config.root == tmp_path
    assert config.project_name == "analytics-workflows"


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


@pytest.mark.parametrize("source", ["model", "python", "environment", "toml"])
def test_explicit_temporary_database_paths_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setattr("quackframe.config._read_dotenv", Mock(return_value={}))
    path = tmp_path / "caller.duckdb"
    path.write_bytes(b"caller-owned")
    database_values = {"mode": "temporary", "path": str(path)}
    error_type = ValueError if source == "model" else ConfigurationError

    with pytest.raises(error_type, match="cannot be used with temporary mode"):
        if source == "model":
            QuackframeConfig.model_validate({"database": database_values})
        elif source == "python":
            load_config(
                root=tmp_path, database_mode="temporary", database_path=path, environ={}
            )
        elif source == "environment":
            load_config(
                root=tmp_path,
                environ={
                    "QUACKFRAME_DATABASE_MODE": "temporary",
                    "QUACKFRAME_DATABASE_PATH": str(path),
                },
            )
        else:
            (tmp_path / "pyproject.toml").write_text(
                "[tool.quackframe.database]\n"
                'mode = "temporary"\npath = "caller.duckdb"',
                encoding="utf-8",
            )
            load_config(root=tmp_path, environ={})
    assert path.read_bytes() == b"caller-owned"


@pytest.mark.parametrize("source", ["python", "environment"])
def test_temporary_override_clears_inherited_persistent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setattr("quackframe.config._read_dotenv", Mock(return_value={}))
    (tmp_path / "pyproject.toml").write_text(
        '[tool.quackframe.database]\nmode = "persistent"\npath = "caller.duckdb"',
        encoding="utf-8",
    )
    config = load_config(
        root=tmp_path,
        database_mode="temporary" if source == "python" else None,
        environ=(
            {"QUACKFRAME_DATABASE_MODE": "temporary"} if source == "environment" else {}
        ),
    )
    assert config.database.mode == "temporary"
    assert config.database.path is None


@pytest.mark.parametrize("explicit", [None, False, True])
def test_error_permission_environment_and_explicit_override(
    tmp_path: Path, explicit: bool | None
) -> None:
    config = load_config(
        root=tmp_path,
        allow_external_error_logging=explicit,
        environ={"QUACKFRAME_ALLOW_EXTERNAL_ERROR_LOGGING": "true"},
    )

    assert config.allow_external_error_logging is (
        True if explicit is None else explicit
    )
    assert config.allow_external_result_logging is False


def test_error_permission_environment_overrides_synthetic_dotenv(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "QUACKFRAME_ALLOW_EXTERNAL_ERROR_LOGGING=true\n", encoding="utf-8"
    )

    assert load_config(root=tmp_path, environ={}).allow_external_error_logging is True
    assert (
        load_config(
            root=tmp_path, environ={"QUACKFRAME_ALLOW_EXTERNAL_ERROR_LOGGING": "false"}
        ).allow_external_error_logging
        is False
    )
