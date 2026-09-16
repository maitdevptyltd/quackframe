"""Prefect Block credential provider."""

from quackframe.sql_functions.register_secret.providers.prefect.provider import (
    PrefectCredentialProvider,
)

__all__ = ["PrefectCredentialProvider"]
