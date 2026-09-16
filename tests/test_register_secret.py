"""Credential-provider and secret-strategy tests without Prefect."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, Mock

import duckdb
import pytest
from duckdb import DuckDBPyConnection
from pydantic import SecretStr

from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_secret import function as function_module
from quackframe.sql_functions.register_secret.function import register_secret
from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringCredentials,
    MssqlCredentials,
)
from quackframe.sql_functions.register_secret.providers.protocol import (
    CredentialProvider,
)
from quackframe.sql_functions.register_secret.strategies import (
    register_resolved_secret,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, list[object] | None]] = []

    def execute(
        self,
        query: str,
        parameters: list[object] | None = None,
    ) -> RecordingConnection:
        self.queries.append((query, parameters))
        return self


def test_public_macro_forwards_named_map_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )
    provider = Mock()
    provider.resolve.return_value = credentials
    register_strategy = Mock()

    def get_provider(_: str) -> CredentialProvider:
        return cast(CredentialProvider, provider)

    monkeypatch.setattr(function_module, "get_provider", get_provider)
    monkeypatch.setattr(function_module, "register_resolved_secret", register_strategy)

    with duckdb.connect() as connection:
        install_functions(connection, ("register_secret",))
        result = connection.execute(
            """
            SELECT quackframe.register_secret(
                provider := 'prefect',
                reference := 'shared-login',
                secret_type := 'mssql',
                alias := 'reporting',
                overrides := MAP {'database': 'Reporting'}
            )
            """
        ).fetchone()

    assert result == (True,)
    provider.resolve.assert_called_once_with("shared-login", "mssql")
    assert register_strategy.call_args.args[1:] == (
        "mssql",
        "reporting",
        credentials,
        {"database": "Reporting"},
    )


def test_register_secret_selects_provider_and_uses_duplicate_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )
    provider = Mock()
    provider.resolve.return_value = credentials
    connection = MagicMock()
    duplicate = Mock()
    connection.duplicate.return_value.__enter__.return_value = duplicate
    register_strategy = Mock()

    def get_provider(_: str) -> CredentialProvider:
        return cast(CredentialProvider, provider)

    monkeypatch.setattr(function_module, "get_provider", get_provider)
    monkeypatch.setattr(function_module, "register_resolved_secret", register_strategy)

    outcome = register_secret(
        connection,
        "prefect",
        "shared-login",
        "mssql",
        "reporting",
        {"database": "Reporting"},
    )

    assert outcome is True
    provider.resolve.assert_called_once_with("shared-login", "mssql")
    register_strategy.assert_called_once_with(
        duplicate,
        "mssql",
        "reporting",
        credentials,
        {"database": "Reporting"},
    )


def test_mssql_override_values_are_typed_and_bound() -> None:
    connection = RecordingConnection()
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    register_resolved_secret(
        cast(DuckDBPyConnection, connection),
        "mssql",
        "reporting",
        credentials,
        {"database": "Reporting", "port": "1444", "use_encrypt": "false"},
    )

    query, parameters = connection.queries[-1]
    assert "sensitive" not in query
    assert 'TEMPORARY SECRET "reporting"' in query
    assert parameters == [
        "sql.example.test",
        1444,
        "Reporting",
        "reader",
        "sensitive",
        False,
    ]


def test_azure_scope_override_is_validated_and_bound() -> None:
    connection = RecordingConnection()
    credentials = AzureConnectionStringCredentials(
        connection_string=SecretStr("sensitive")
    )

    register_resolved_secret(
        cast(DuckDBPyConnection, connection),
        "azure_connection_string",
        "storage",
        credentials,
        {"scope": "az://container/reports/"},
    )

    query, parameters = connection.queries[-1]
    assert "sensitive" not in query
    assert parameters == ["sensitive", "az://container/reports/"]


@pytest.mark.parametrize("field", ["user", "password", "connection_string"])
def test_secret_bearing_overrides_are_rejected(field: str) -> None:
    connection = MagicMock()

    with pytest.raises(ValueError, match="Unsupported mssql override"):
        register_secret(
            connection,
            "prefect",
            "shared-login",
            "mssql",
            overrides={field: "must-not-pass"},
        )


def test_database_is_required_after_override_merge() -> None:
    connection = RecordingConnection()
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="database is required"):
        register_resolved_secret(
            cast(DuckDBPyConnection, connection),
            "mssql",
            "reporting",
            credentials,
            {},
        )


def test_blank_override_does_not_fall_back_to_block_value() -> None:
    connection = RecordingConnection()
    credentials = MssqlCredentials(
        host="sql.example.test",
        database="DefaultDatabase",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="database is required"):
        register_resolved_secret(
            cast(DuckDBPyConnection, connection),
            "mssql",
            "reporting",
            credentials,
            {"database": ""},
        )
