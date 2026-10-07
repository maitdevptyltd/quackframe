"""Prefect Block for Azure Storage managed-identity access."""

from typing import TypeVar

from prefect.blocks.core import Block

from quackframe.credential_loading.models import (
    AzureManagedIdentityCredentials as Credential,
)
from quackframe.credential_loading.models import CredentialModel

T = TypeVar("T", bound=CredentialModel)


class AzureManagedIdentityCredentials(Block):
    """Store account and identity selection with an optional storage scope.

    ``scope`` may be supplied later by the allowlisted Quackframe override.
    """

    account_name: str
    client_id: str | None = None
    scope: str | None = None

    def to_credentials(self, model_type: type[T]) -> T:
        """Construct a compatible strategy directly from this Block's fields."""

        if not issubclass(model_type, Credential):
            raise ValueError("Incompatible azure_managed_identity credential model")
        return model_type(
            account_name=self.account_name,
            client_id=self.client_id,
            scope=self.scope,
        )
