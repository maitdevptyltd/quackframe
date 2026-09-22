"""Prefect Block for private-key SSH credentials."""

from prefect.blocks.core import Block
from pydantic import Field, SecretStr


class SshPrivateKeyCredentials(Block):
    """Store private-key SSH authentication and connection details in Prefect.

    Reviewed SQL may replace ``scope`` through Quackframe's allowlisted
    override while authentication and connection settings remain protected.
    """

    username: SecretStr
    key_path: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    scope: str = Field(min_length=1)
