"""Load project intent into one typed Quackframe configuration."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from quackframe.errors import ConfigurationError
from quackframe.runtimes.registry import runtime_names

RuntimeName = str
DatabaseMode = Literal["memory", "temporary", "persistent"]
LogSetting = Literal["annotations-only", "none", "all"]
LOG_SETTINGS: tuple[LogSetting, ...] = ("annotations-only", "none", "all")

_INVOCATION_ONLY_SETTINGS = (
    "log_setting",
    "allow_external_result_logging",
)


class DatabaseConfig(BaseModel):
    """Control where one Quackframe run stores its DuckDB database.

    Memory and temporary databases are owned by Quackframe. Persistent files
    are caller-owned and are never deleted during normal cleanup.
    """

    model_config = ConfigDict(extra="forbid")

    mode: DatabaseMode = "memory"
    path: Path | None = None

    @model_validator(mode="after")
    def validate_path(self) -> DatabaseConfig:
        """Reject storage modes and paths that disagree about file ownership."""

        if self.mode == "memory" and self.path is not None:
            raise ValueError("database.path cannot be used with memory mode")
        if self.mode == "persistent" and self.path is None:
            raise ValueError("database.path is required with persistent mode")
        return self


class FunctionsConfig(BaseModel):
    """List the SQL-callable Quackframe functions enabled for this project.

    The empty default exposes no Python functions to project SQL.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: tuple[str, ...] = ()


class DuckDBConfig(BaseModel):
    """Describe how Quackframe prepares a DuckDB session.

    ``settings`` contains connection options such as ``threads``,
    ``memory_limit``, and ``temp_directory``.

    ``extensions`` lists DuckDB add-ons such as ``azure`` and ``mssql``, which
    are installed and loaded before SQL files run.
    """

    model_config = ConfigDict(extra="forbid")

    settings: dict[str, str] = Field(default_factory=dict)
    extensions: tuple[str, ...] = ()


class QuackframeConfig(BaseModel):
    """Hold the final settings used by every Quackframe runtime.

    ``project_name`` records the downstream package name when configuration is
    loaded from ``pyproject.toml``. Optional runtimes may use it for display,
    but it does not change core execution semantics.
    """

    model_config = ConfigDict(extra="forbid")

    root: Path = Field(default_factory=Path.cwd)
    runtime: RuntimeName = "direct"
    project_name: str | None = Field(default=None, exclude=True, repr=False)
    log_setting: LogSetting = "annotations-only"
    allow_external_result_logging: bool = False
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    functions: FunctionsConfig = Field(default_factory=FunctionsConfig)
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)

    @field_validator("runtime")
    @classmethod
    def runtime_must_be_registered(cls, value: str) -> str:
        """Keep configuration validation aligned with the runtime registry."""

        if value not in runtime_names():
            available = ", ".join(runtime_names())
            raise ValueError(f"runtime must be one of: {available}")
        return value

    @model_validator(mode="after")
    def resolve_paths(self) -> QuackframeConfig:
        """Resolve every relative filesystem setting from the runtime root."""

        self.root = self.root.expanduser().resolve()
        if self.database.path is not None and not self.database.path.is_absolute():
            self.database.path = self.root / self.database.path
        return self


def load_config(
    *,
    config_path: str | Path | None = None,
    root: str | Path | None = None,
    runtime: RuntimeName | None = None,
    log_setting: LogSetting | None = None,
    allow_external_result_logging: bool | None = None,
    database_mode: DatabaseMode | None = None,
    database_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> QuackframeConfig:
    """Build the final configuration for one Quackframe run.

    Project TOML is the lowest-precedence input. Environment values override
    it, and explicit Python or CLI values win over both. All inputs pass through
    the same typed model before execution begins.
    """

    environment = os.environ if environ is None else environ
    initial_root = (
        Path(root or environment.get("QUACKFRAME_ROOT") or Path.cwd())
        .expanduser()
        .resolve()
    )
    source_path = (
        Path(config_path)
        if config_path is not None
        else initial_root / "pyproject.toml"
    )

    data, project_name = _read_project_config(
        source_path,
        required=config_path is not None,
    )
    data = _merge(data, _environment_config(environment))
    data = _merge(
        data,
        _explicit_config(
            root=root,
            runtime=runtime,
            log_setting=log_setting,
            allow_external_result_logging=allow_external_result_logging,
            database_mode=database_mode,
            database_path=database_path,
        ),
    )
    data.setdefault("root", str(initial_root))
    data.setdefault("project_name", project_name)

    try:
        return QuackframeConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigurationError(_validation_reason(error)) from None


def _read_project_config(
    path: Path,
    *,
    required: bool,
) -> tuple[dict[str, Any], str | None]:
    """Read Quackframe settings and the downstream project name from TOML."""

    if not path.is_file():
        if required:
            raise ConfigurationError(f"Configuration file does not exist: {path}")
        return {}, None

    try:
        project = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(
            f"Could not read configuration file: {path}: {error}"
        ) from None

    tool_value = project.get("tool", {})
    if not isinstance(tool_value, dict):
        raise ConfigurationError("[tool] must be a TOML table")
    tool = cast(dict[str, Any], tool_value)
    quackframe = tool.get("quackframe", {})
    if not isinstance(quackframe, dict):
        raise ConfigurationError("[tool.quackframe] must be a TOML table")
    for setting in _INVOCATION_ONLY_SETTINGS:
        if setting in quackframe:
            raise ConfigurationError(
                f"[tool.quackframe].{setting} is not allowed; "
                "use an environment or invocation value"
            )
    project_value = project.get("project", {})
    project_name = None
    if isinstance(project_value, dict):
        project_table = cast(dict[str, Any], project_value)
        candidate = project_table.get("name")
        if isinstance(candidate, str) and candidate.strip():
            project_name = candidate
    return cast(dict[str, Any], quackframe), project_name


def _environment_config(environment: Mapping[str, str]) -> dict[str, Any]:
    """Translate supported environment variables into configuration fields."""

    values: dict[str, Any] = {}
    if value := environment.get("QUACKFRAME_ROOT"):
        values["root"] = value
    if value := environment.get("QUACKFRAME_RUNTIME"):
        values["runtime"] = value
    if value := environment.get("QUACKFRAME_LOG_SETTING"):
        values["log_setting"] = value
    if value := environment.get("QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING"):
        values["allow_external_result_logging"] = value
    if value := environment.get("QUACKFRAME_DATABASE_MODE"):
        values.setdefault("database", {})["mode"] = value
        if value in {"memory", "temporary"}:
            values["database"]["path"] = None
    if value := environment.get("QUACKFRAME_DATABASE_PATH"):
        values.setdefault("database", {})["path"] = value
        if "QUACKFRAME_DATABASE_MODE" not in environment:
            values["database"]["mode"] = "persistent"
    if value := environment.get("DUCKDB_TEMP_DIRECTORY"):
        values.setdefault("duckdb", {}).setdefault("settings", {})["temp_directory"] = (
            value
        )
    return values


def _explicit_config(
    *,
    root: str | Path | None,
    runtime: RuntimeName | None,
    log_setting: LogSetting | None,
    allow_external_result_logging: bool | None,
    database_mode: DatabaseMode | None,
    database_path: str | Path | None,
) -> dict[str, Any]:
    """Translate one-run Python or CLI values into configuration fields."""

    values: dict[str, Any] = {}
    if root is not None:
        values["root"] = str(root)
    if runtime is not None:
        values["runtime"] = runtime
    if log_setting is not None:
        values["log_setting"] = log_setting
    if allow_external_result_logging is not None:
        values["allow_external_result_logging"] = allow_external_result_logging
    if database_mode is not None:
        values.setdefault("database", {})["mode"] = database_mode
        if database_mode in {"memory", "temporary"}:
            values["database"]["path"] = None
    if database_path is not None:
        values.setdefault("database", {})["path"] = str(database_path)
    return values


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge nested configuration tables by precedence."""

    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            typed_existing = cast(dict[str, Any], existing)
            typed_value = cast(dict[str, Any], value)
            merged[key] = _merge(typed_existing, typed_value)
        else:
            merged[key] = value
    return merged


def _validation_reason(error: ValidationError) -> str:
    """Render the first Pydantic issue as a concise configuration error."""

    issue = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in issue["loc"])
    return f"Invalid Quackframe configuration at {location}: {issue['msg']}"
