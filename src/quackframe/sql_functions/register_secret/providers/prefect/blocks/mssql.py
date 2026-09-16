"""Prefect Block for DuckDB MSSQL credentials."""

from prefect.blocks.core import Block
from pydantic import Field, SecretStr


class MssqlCredentials(Block):
    """Reusable SQL Server authentication with an optional database."""

    host: str = Field(min_length=1)
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = Field(default=1433, ge=1, le=65535)
    use_encrypt: bool = True
