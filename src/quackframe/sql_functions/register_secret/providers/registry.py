"""Register and lazily load credential providers for ``register_secret``."""

from dataclasses import dataclass
from importlib import import_module
from typing import cast

from quackframe.errors import OptionalDependencyError
from quackframe.sql_functions.register_secret.providers.protocol import (
    CredentialProvider,
)


@dataclass(frozen=True)
class ProviderRegistration:
    """Describe a public provider and the optional implementation that owns it."""

    name: str
    module_name: str
    implementation_name: str
    missing_dependency: str
    missing_dependency_message: str

    def load(self) -> CredentialProvider:
        """Import and construct this provider only after SQL selects it."""

        # Provider selection is the optional-dependency boundary. Enabling the
        # generic SQL function must not import every available credential store.
        try:
            module = import_module(self.module_name)
        except ModuleNotFoundError as error:
            if error.name == self.missing_dependency or (
                error.name is not None
                and error.name.startswith(f"{self.missing_dependency}.")
            ):
                raise OptionalDependencyError(self.missing_dependency_message) from None
            raise
        provider_type = getattr(module, self.implementation_name)
        return cast(CredentialProvider, provider_type())


PROVIDER_REGISTRY: tuple[ProviderRegistration, ...] = (
    ProviderRegistration(
        name="prefect",
        module_name=(
            "quackframe.sql_functions.register_secret.providers.prefect.provider"
        ),
        implementation_name="PrefectCredentialProvider",
        missing_dependency="prefect",
        missing_dependency_message=(
            "The Prefect credential provider requires 'quackframe[prefect]'"
        ),
    ),
)


def get_provider(name: str) -> CredentialProvider:
    """Load the credential provider registered under its public SQL name."""

    for registration in PROVIDER_REGISTRY:
        if registration.name == name:
            return registration.load()
    raise ValueError(f"Unsupported credential provider: {name}")
