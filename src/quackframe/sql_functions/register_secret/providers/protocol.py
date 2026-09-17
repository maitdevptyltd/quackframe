"""Provider contract independent of concrete credential stores."""

from typing import Protocol

from quackframe.sql_functions.register_secret.models import DuckDBSecret


class CredentialProvider(Protocol):
    """Translate one external reference into a Quackframe DuckDB secret."""

    def resolve(self, reference: str, secret_type: str) -> DuckDBSecret:
        """Load a stored credential and return a matching DuckDB secret."""

        ...
