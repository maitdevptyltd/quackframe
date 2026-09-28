"""Prefect Block for Azure Storage managed-identity access."""

from prefect.blocks.core import Block


class AzureManagedIdentityCredentials(Block):
    """Store account and identity selection with an optional storage scope.

    ``scope`` may be supplied later by the allowlisted Quackframe override.
    """

    account_name: str
    client_id: str | None = None
    scope: str | None = None
