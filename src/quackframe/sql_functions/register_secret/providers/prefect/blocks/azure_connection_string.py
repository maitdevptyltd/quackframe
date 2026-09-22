"""Prefect Block for an Azure Storage connection string."""

from prefect.blocks.core import Block
from pydantic import SecretStr


class AzureConnectionStringCredentials(Block):
    """Store an Azure connection string and optional scope in Prefect.

    ``scope`` may be supplied later by the allowlisted Quackframe override.
    """

    connection_string: SecretStr
    scope: str | None = None
