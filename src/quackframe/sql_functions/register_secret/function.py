"""SQL-callable temporary secret registration."""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from quackframe.sql_functions.register_secret.providers.registry import get_provider
from quackframe.sql_functions.register_secret.validation import validate_identifier


def register_secret(
    connection: DuckDBPyConnection,
    provider: str,
    reference: str,
    secret_type: str,
    alias: str | None = None,
    overrides: dict[str, str] | None = None,
) -> bool:
    """Resolve and register one temporary DuckDB secret.

    SQL supplies only a provider reference, a validated alias, and non-sensitive
    overrides. The selected provider returns a Quackframe secret model that
    owns override validation, extension loading, and registration.
    """

    # Provider references may contain dashes, but the generated DuckDB secret
    # alias is deliberately limited to simple SQL identifier characters.
    resolved_alias = validate_identifier(
        alias or reference.replace("-", "_"),
        "secret alias",
    )
    credential_provider = get_provider(provider)
    secret = credential_provider.resolve(reference, secret_type)
    resolved_secret = secret.resolve_overrides(overrides or {})

    # The active connection is already running this SQL function. A short-lived
    # duplicate reaches the same database without trying to reuse that busy
    # connection, and keeps this special behaviour inside register_secret.
    with connection.duplicate() as secret_connection:
        resolved_secret.register(secret_connection, resolved_alias)
    return True
