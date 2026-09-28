"""Compatibility imports for the shared credential provider."""

from quackframe.credential_providers.prefect.blocks import (
    AzureConnectionStringCredentials,
    AzureManagedIdentityCredentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)

__all__ = [
    "AzureConnectionStringCredentials",
    "AzureManagedIdentityCredentials",
    "MssqlCredentials",
    "SshPrivateKeyCredentials",
]
