"""Typed provider contract independent of credential stores and registration."""

from typing import Protocol, TypeVar

from quackframe.credential_loading.models import CredentialModel

T = TypeVar("T", bound=CredentialModel)


class CredentialProvider(Protocol):
    """Construct the requested strategy from one stored credential."""

    def resolve(self, reference: str, model_type: type[T]) -> T:
        """Load one document and construct a compatible concrete model."""

        ...
