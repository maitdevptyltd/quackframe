"""Lazy registry for function-owned credential providers."""

from importlib import import_module

from quackframe.errors import OptionalDependencyError
from quackframe.sql_functions.register_secret.providers.protocol import (
    CredentialProvider,
)


def get_provider(name: str) -> CredentialProvider:
    if name != "prefect":
        raise ValueError(f"Unsupported credential provider: {name}")

    try:
        module = import_module(
            "quackframe.sql_functions.register_secret.providers.prefect.provider"
        )
    except ModuleNotFoundError as error:
        if error.name == "prefect":
            raise OptionalDependencyError(
                "The Prefect credential provider requires 'quackframe[prefect]'"
            ) from None
        raise
    return module.PrefectCredentialProvider()
