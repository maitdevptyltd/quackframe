"""Resolve credential strategies directly from Quackframe Prefect Blocks."""

from typing import TypeVar, cast

from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.providers.prefect.blocks import (
    AzureConnectionStringCredentials,
    AzureManagedIdentityCredentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)

T = TypeVar("T", bound=CredentialModel)
CredentialBlock = (
    MssqlCredentials
    | AzureConnectionStringCredentials
    | AzureManagedIdentityCredentials
    | SshPrivateKeyCredentials
)
BLOCK_TYPES: dict[str, type[CredentialBlock]] = {
    "mssql": MssqlCredentials,
    "azure_connection_string": AzureConnectionStringCredentials,
    "azure_managed_identity": AzureManagedIdentityCredentials,
    "ssh_private_key": SshPrivateKeyCredentials,
}


class PrefectCredentialProvider:
    """Load one Block and let it construct the requested compatible model."""

    def resolve(self, reference: str, model_type: type[T]) -> T:
        """Load one Block and construct the requested credential strategy."""

        block_type = BLOCK_TYPES.get(model_type.credential_type)
        if block_type is None:
            raise ValueError("Unsupported Prefect credential type")

        block_name = self._block_name(reference)
        try:
            block = cast(CredentialBlock, block_type.load(block_name))
            return block.to_credentials(model_type)
        except Exception:  # Prefect exposes several client and validation failures.
            raise RuntimeError(
                f"Prefect credential block '{reference}' could not be loaded. "
                "Confirm that it exists in the configured Prefect API."
            ) from None

    @staticmethod
    def _block_name(reference: str) -> str:
        """Translate a SQL-friendly reference into a Prefect document name."""

        # Prefect cannot store the underscored alternative, so both spellings
        # identify the same document without collapsing two valid references.
        return reference.replace("_", "-")
