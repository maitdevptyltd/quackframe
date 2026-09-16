"""Translate resolved credentials into parameter-bound DuckDB secrets."""

from __future__ import annotations

from collections.abc import Mapping

from duckdb import DuckDBPyConnection
from pydantic import ValidationError

from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringCredentials,
    Credential,
    MssqlCredentials,
    SecretType,
)
from quackframe.sql_functions.register_secret.validation import (
    parse_boolean,
    validate_azure_scope,
)


def register_resolved_secret(
    connection: DuckDBPyConnection,
    secret_type: SecretType,
    alias: str,
    credentials: Credential,
    overrides: Mapping[str, str],
) -> None:
    if secret_type == "mssql" and isinstance(credentials, MssqlCredentials):
        _register_mssql(connection, alias, credentials, overrides)
        return
    if secret_type == "azure_connection_string" and isinstance(
        credentials, AzureConnectionStringCredentials
    ):
        _register_azure(connection, alias, credentials, overrides)
        return
    raise TypeError(f"Credential provider returned the wrong shape for {secret_type}")


def _register_mssql(
    connection: DuckDBPyConnection,
    alias: str,
    credentials: MssqlCredentials,
    overrides: Mapping[str, str],
) -> None:
    updates: dict[str, object] = {}
    if "database" in overrides:
        updates["database"] = overrides["database"]
    if "port" in overrides:
        try:
            updates["port"] = int(overrides["port"])
        except ValueError:
            raise ValueError("port override must be an integer") from None
    if "use_encrypt" in overrides:
        updates["use_encrypt"] = parse_boolean(overrides["use_encrypt"])

    values = credentials.model_dump()
    values.update(updates)
    try:
        resolved = MssqlCredentials.model_validate(values)
    except ValidationError:
        raise ValueError("MSSQL credential fields are invalid") from None
    if not resolved.database:
        raise ValueError("MSSQL database is required in the block or overrides")

    connection.execute("INSTALL mssql FROM community")
    connection.execute("LOAD mssql")
    connection.execute(
        f'''
        CREATE OR REPLACE TEMPORARY SECRET "{alias}" (
            TYPE mssql,
            host ?,
            port ?,
            database ?,
            user ?,
            password ?,
            use_encrypt ?
        )
        ''',
        [
            resolved.host,
            resolved.port,
            resolved.database,
            resolved.user.get_secret_value(),
            resolved.password.get_secret_value(),
            resolved.use_encrypt,
        ],
    )


def _register_azure(
    connection: DuckDBPyConnection,
    alias: str,
    credentials: AzureConnectionStringCredentials,
    overrides: Mapping[str, str],
) -> None:
    scope = overrides.get("scope", credentials.scope)
    if scope is None:
        raise ValueError("Azure scope is required in the block or overrides")
    scope = validate_azure_scope(scope)

    connection.execute("INSTALL azure")
    connection.execute("LOAD azure")
    connection.execute(
        f'''
        CREATE OR REPLACE TEMPORARY SECRET "{alias}" (
            TYPE azure,
            PROVIDER config,
            CONNECTION_STRING ?,
            SCOPE ?
        )
        ''',
        [credentials.connection_string.get_secret_value(), scope],
    )
