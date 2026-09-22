"""Quackframe-owned Prefect Block definitions."""

from .azure_connection_string import (
    AzureConnectionStringCredentials,
)
from .mssql import (
    MssqlCredentials,
)
from .ssh_private_key import SshPrivateKeyCredentials

__all__ = [
    "AzureConnectionStringCredentials",
    "MssqlCredentials",
    "SshPrivateKeyCredentials",
]
