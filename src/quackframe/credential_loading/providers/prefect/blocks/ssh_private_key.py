"""Prefect Block for private-key SSH credentials."""

from typing import TypeVar

from prefect.blocks.core import Block
from pydantic import Field, SecretStr

from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.models import SshPrivateKeyCredentials as Credential

T = TypeVar("T", bound=CredentialModel)


class SshPrivateKeyCredentials(Block):
    """Store private-key SSH authentication and connection details in Prefect.

    Reviewed SQL may replace ``scope`` through Quackframe's allowlisted
    override while authentication and connection settings remain protected.
    """

    username: SecretStr
    key_path: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    scope: str = Field(min_length=1)

    def to_credentials(self, model_type: type[T]) -> T:
        """Construct a compatible strategy directly from this Block's fields."""

        if not issubclass(model_type, Credential):
            raise ValueError("Incompatible ssh_private_key credential model")
        return model_type(
            username=self.username,
            key_path=self.key_path,
            port=self.port,
            scope=self.scope,
        )
