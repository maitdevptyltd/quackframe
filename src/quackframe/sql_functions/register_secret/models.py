"""Credential shapes and non-sensitive overrides owned by register_secret."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

SecretType = Literal["mssql", "azure_connection_string"]


class MssqlCredentials(BaseModel):
    """Resolved fields accepted by DuckDB's MSSQL secret provider."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = Field(default=1433, ge=1, le=65535)
    use_encrypt: bool = True


class AzureConnectionStringCredentials(BaseModel):
    """Resolved Azure connection string and optional DuckDB scope."""

    model_config = ConfigDict(extra="forbid")

    connection_string: SecretStr
    scope: str | None = None

    @field_validator("connection_string")
    @classmethod
    def connection_string_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Connection string must not be blank")
        return value


Credential = MssqlCredentials | AzureConnectionStringCredentials
