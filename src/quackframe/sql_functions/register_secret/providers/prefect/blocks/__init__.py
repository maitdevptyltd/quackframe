"""Quackframe-owned Prefect Block definitions."""

from .azure_connection_string import (
    AzureConnectionStringCredentials,
)
from .mssql import (
    MssqlCredentials,
)

__all__ = ["AzureConnectionStringCredentials", "MssqlCredentials"]
