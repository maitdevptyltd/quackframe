"""Prefect Block for an Azure Storage connection string."""

from typing import TypeVar

from prefect.blocks.core import Block
from pydantic import SecretStr

from quackframe.credential_loading.models import (
    AzureConnectionStringCredentials as Credential,
)
from quackframe.credential_loading.models import CredentialModel

T = TypeVar("T", bound=CredentialModel)


class AzureConnectionStringCredentials(Block):
    """Store an Azure connection string and optional scope in Prefect.

    ``scope`` may be supplied later by the allowlisted Quackframe override.
    """

    connection_string: SecretStr
    scope: str | None = None

    def to_credentials(self, model_type: type[T]) -> T:
        """Construct a compatible strategy directly from this Block's fields."""

        if not issubclass(model_type, Credential):
            raise ValueError("Incompatible azure_connection_string credential model")
        return model_type(
            connection_string=self.connection_string,
            scope=self.scope,
        )
