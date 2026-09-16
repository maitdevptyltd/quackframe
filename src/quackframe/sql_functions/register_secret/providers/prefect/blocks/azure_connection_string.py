"""Prefect Block for an Azure Storage connection string."""

from prefect.blocks.core import Block
from pydantic import SecretStr, field_validator


class AzureConnectionStringCredentials(Block):
    """Reusable Azure connection string with an optional storage scope."""

    connection_string: SecretStr
    scope: str | None = None

    @field_validator("connection_string")
    @classmethod
    def connection_string_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Connection string must not be blank")
        return value
