"""SQL-callable temporary secret registration."""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from quackframe.sql_functions.register_secret.providers.registry import get_provider
from quackframe.sql_functions.register_secret.strategies import (
    register_resolved_secret,
)
from quackframe.sql_functions.register_secret.validation import (
    parse_secret_type,
    validate_identifier,
    validate_overrides,
)


def register_secret(
    connection: DuckDBPyConnection,
    provider: str,
    reference: str,
    secret_type: str,
    alias: str | None = None,
    overrides: dict[str, str] | None = None,
) -> bool:
    """Resolve a stored credential and register a temporary DuckDB secret."""

    resolved_type = parse_secret_type(secret_type)
    resolved_alias = validate_identifier(
        alias or reference.replace("-", "_"),
        "secret alias",
    )
    resolved_overrides = validate_overrides(
        resolved_type,
        overrides,
    )
    credential_provider = get_provider(provider)
    credentials = credential_provider.resolve(reference, resolved_type)

    # The active connection is executing this UDF. Its duplicate can mutate the
    # same DuckDB instance without re-entering the active query.
    with connection.duplicate() as secret_connection:
        register_resolved_secret(
            secret_connection,
            resolved_type,
            resolved_alias,
            credentials,
            resolved_overrides,
        )
    return True
