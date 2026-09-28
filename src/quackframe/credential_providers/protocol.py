"""Provider contract independent of concrete credential stores."""

from typing import Protocol

from quackframe.credential_providers.models import Credentials


class CredentialProvider(Protocol):
    """Translate one external reference into typed Quackframe credentials."""

    def resolve(self, reference: str, secret_type: str) -> Credentials:
        """Load a stored credential and return matching backend-independent data."""

        ...
