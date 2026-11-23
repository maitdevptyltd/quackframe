"""Load and resolve credentials once without choosing a registration operation."""

from collections.abc import Mapping
from typing import TypeVar

from pydantic import ValidationError

from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.providers.registry import get_provider

T = TypeVar("T", bound=CredentialModel)


def load_credentials(
    provider: str,
    reference: str,
    model_type: type[T],
    overrides: Mapping[str, str] | None = None,
) -> T:
    """Select a provider, load one strategy, and apply its immutable overrides."""

    credential_provider = get_provider(provider)
    try:
        credentials = credential_provider.resolve(reference, model_type)
        return credentials.resolve_overrides(overrides or {})
    except ValidationError:
        # Pydantic diagnostics may contain the provider's original input values.
        raise ValueError("Credential fields or overrides are invalid") from None
