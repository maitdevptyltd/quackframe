"""Credential-provider and DuckDB-secret model tests without Prefect."""

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
    DuckDBSecret,
    MssqlCredentials,
)
from quackframe.sql_functions.register_secret.providers import registry
from quackframe.sql_functions.register_secret.providers.protocol import (
    CredentialProvider,
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
    credentials = Mock(spec=DuckDBSecret)
    provider = Mock()
    provider.resolve.return_value = credentials
    resolved_secret = Mock()
    credentials.resolve_overrides.return_value = resolved_secret

    def get_provider(_: str) -> CredentialProvider:
        return cast(CredentialProvider, provider)

    monkeypatch.setattr(function_module, "get_provider", get_provider)

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
    credentials.resolve_overrides.assert_called_once_with({"database": "Reporting"})
    resolved_secret.register.assert_called_once()
    assert resolved_secret.register.call_args.args[1] == "reporting"


def test_register_secret_selects_provider_and_uses_duplicate_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = Mock(spec=DuckDBSecret)
    provider = Mock()
    provider.resolve.return_value = credentials
    connection = MagicMock()
    duplicate = Mock()
    connection.duplicate.return_value.__enter__.return_value = duplicate
    resolved_secret = Mock(spec=DuckDBSecret)
    credentials.resolve_overrides.return_value = resolved_secret

    def get_provider(_: str) -> CredentialProvider:
        return cast(CredentialProvider, provider)

    monkeypatch.setattr(function_module, "get_provider", get_provider)

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
    credentials.resolve_overrides.assert_called_once_with({"database": "Reporting"})
    resolved_secret.register.assert_called_once_with(duplicate, "reporting")


def test_mssql_override_values_are_typed_and_bound() -> None:
    connection = RecordingConnection()
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    resolved = credentials.resolve_overrides(
        {"database": "Reporting", "port": "1444", "use_encrypt": "false"},
    )
    resolved.register(cast(DuckDBPyConnection, connection), "reporting")

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


def test_mssql_rejects_an_invalid_encryption_override() -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        database="Reporting",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="use_encrypt override must be true or false"):
        credentials.resolve_overrides({"use_encrypt": "sometimes"})


def test_azure_scope_override_is_validated_and_bound() -> None:
    connection = RecordingConnection()
    credentials = AzureConnectionStringCredentials(
        connection_string=SecretStr("sensitive")
    )

    resolved = credentials.resolve_overrides({"scope": "az://container/reports/"})
    resolved.register(cast(DuckDBPyConnection, connection), "storage")

    query, parameters = connection.queries[-1]
    assert "sensitive" not in query
    assert parameters == ["sensitive", "az://container/reports/"]


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ("https://storage.example.test/reports/", "must use an az://"),
        ("az://container/reports", "must end with a trailing slash"),
        ("az:///", "must identify a storage location"),
    ],
)
def test_azure_rejects_an_invalid_scope(scope: str, message: str) -> None:
    credentials = AzureConnectionStringCredentials(
        connection_string=SecretStr("sensitive")
    )

    with pytest.raises(ValueError, match=message):
        credentials.resolve_overrides({"scope": scope})


@pytest.mark.parametrize("field", ["user", "password", "connection_string"])
def test_secret_bearing_overrides_are_rejected(field: str) -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="Unsupported mssql override"):
        credentials.resolve_overrides({field: "must-not-pass"})


def test_database_is_required_after_override_merge() -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="database is required"):
        credentials.resolve_overrides({})


def test_blank_override_does_not_fall_back_to_block_value() -> None:
    credentials = MssqlCredentials(
        host="sql.example.test",
        database="DefaultDatabase",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with pytest.raises(ValueError, match="database is required"):
        credentials.resolve_overrides({"database": ""})


def test_register_secret_installs_without_prefect() -> None:
    with duckdb.connect() as connection:
        install_functions(connection, ("register_secret",))

        macro = connection.execute(
            "SELECT function_name FROM duckdb_functions() "
            "WHERE schema_name = 'quackframe' AND function_name = 'register_secret'"
        ).fetchone()

    assert macro == ("register_secret",)


def test_provider_registry_loads_an_added_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock(spec=CredentialProvider)
    module = Mock()
    module.ExampleProvider.return_value = provider
    registration = registry.ProviderRegistration(
        name="example",
        module_name="example.provider",
        implementation_name="ExampleProvider",
        missing_dependency="example",
        missing_dependency_message="Install example support",
    )
    monkeypatch.setattr(registry, "PROVIDER_REGISTRY", (registration,))
    monkeypatch.setattr(registry, "import_module", Mock(return_value=module))

    assert registry.get_provider("example") is provider
