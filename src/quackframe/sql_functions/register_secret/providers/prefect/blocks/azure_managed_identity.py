"""Compatibility imports for the shared credential provider."""

from quackframe.credential_providers.prefect.blocks.azure_managed_identity import (
    AzureManagedIdentityCredentials,
)

__all__ = ["AzureManagedIdentityCredentials"]
