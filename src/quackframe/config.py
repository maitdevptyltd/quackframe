"""Load project intent into one typed Quackframe configuration."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from quackframe.errors import ConfigurationError

RuntimeName = Literal["direct", "prefect"]
DatabaseMode = Literal["memory", "temporary", "persistent"]


class DatabaseConfig(BaseModel):
    """DuckDB storage lifecycle for one invocation."""

    model_config = ConfigDict(extra="forbid")

    mode: DatabaseMode = "memory"
    path: Path | None = None

    @model_validator(mode="after")
    def validate_path(self) -> DatabaseConfig:
        if self.mode == "memory" and self.path is not None:
            raise ValueError("database.path cannot be used with memory mode")
        if self.mode == "persistent" and self.path is None:
            raise ValueError("database.path is required with persistent mode")
        return self


class FunctionsConfig(BaseModel):
    """Reviewable allowlist of SQL-callable Quackframe functions."""

    model_config = ConfigDict(extra="forbid")

    enabled: tuple[str, ...] = ()


class DuckDBConfig(BaseModel):
    """Small, explicit surface for DuckDB connection settings."""

    model_config = ConfigDict(extra="forbid")

    settings: dict[str, str] = Field(default_factory=dict)
    extensions: tuple[str, ...] = ()


class QuackframeConfig(BaseModel):
    """Canonical framework-independent configuration."""

    model_config = ConfigDict(extra="forbid")

    root: Path = Field(default_factory=Path.cwd)
    runtime: RuntimeName = "direct"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    functions: FunctionsConfig = Field(default_factory=FunctionsConfig)
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)

    @model_validator(mode="after")
    def resolve_paths(self) -> QuackframeConfig:
        self.root = self.root.expanduser().resolve()
        if self.database.path is not None and not self.database.path.is_absolute():
            self.database.path = self.root / self.database.path
        return self


def load_config(
    *,
    config_path: str | Path | None = None,
    root: str | Path | None = None,
    runtime: RuntimeName | None = None,
    database_mode: DatabaseMode | None = None,
    database_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> QuackframeConfig:
    """Merge defaults, TOML, environment, and explicit values in that order."""

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

    data = _read_project_config(source_path, required=config_path is not None)
    data = _merge(data, _environment_config(environment))
    data = _merge(
        data,
        _explicit_config(
            root=root,
            runtime=runtime,
            database_mode=database_mode,
            database_path=database_path,
        ),
    )
    data.setdefault("root", str(initial_root))

    try:
        return QuackframeConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigurationError(_validation_reason(error)) from None


def _read_project_config(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigurationError(f"Configuration file does not exist: {path}")
        return {}

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
    return cast(dict[str, Any], quackframe)


def _environment_config(environment: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if value := environment.get("QUACKFRAME_ROOT"):
        values["root"] = value
    if value := environment.get("QUACKFRAME_RUNTIME"):
        values["runtime"] = value
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
    database_mode: DatabaseMode | None,
    database_path: str | Path | None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if root is not None:
        values["root"] = str(root)
    if runtime is not None:
        values["runtime"] = runtime
    if database_mode is not None:
        values.setdefault("database", {})["mode"] = database_mode
        if database_mode in {"memory", "temporary"}:
            values["database"]["path"] = None
    if database_path is not None:
        values.setdefault("database", {})["path"] = str(database_path)
    return values


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
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
    issue = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in issue["loc"])
    return f"Invalid Quackframe configuration at {location}: {issue['msg']}"
