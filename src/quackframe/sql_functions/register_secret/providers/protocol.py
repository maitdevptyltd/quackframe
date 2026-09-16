"""Provider contract independent of concrete credential stores."""

from typing import Protocol

from quackframe.sql_functions.register_secret.models import Credential, SecretType


class CredentialProvider(Protocol):
    """Resolve one reference without exposing its secret values."""

    def resolve(self, reference: str, secret_type: SecretType) -> Credential: ...
