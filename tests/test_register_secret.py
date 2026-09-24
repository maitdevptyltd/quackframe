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
    AzureManagedIdentityCredentials,
    DuckDBSecret,
    MssqlCredentials,
    SshPrivateKeyCredentials,
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


def test_register_secret_derives_a_duckdb_alias_from_a_dashed_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = Mock(spec=DuckDBSecret)
    resolved_secret = Mock(spec=DuckDBSecret)
    credentials.resolve_overrides.return_value = resolved_secret
    provider = Mock()
    provider.resolve.return_value = credentials
    connection = MagicMock()
    duplicate = Mock()
    connection.duplicate.return_value.__enter__.return_value = duplicate

    def get_provider(_: str) -> CredentialProvider:
        return cast(CredentialProvider, provider)

    monkeypatch.setattr(function_module, "get_provider", get_provider)

    register_secret(
        connection,
        "prefect",
        "shared-login",
        "mssql",
    )

    provider.resolve.assert_called_once_with("shared-login", "mssql")
    resolved_secret.register.assert_called_once_with(duplicate, "shared_login")


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


@pytest.mark.parametrize("client_id", [None, "identity'client"])
@pytest.mark.parametrize(
    "scope", ["az://container/", "azure://container/", "abfss://container/"]
)
def test_azure_managed_identity_registration_binds_values(
    client_id: str | None,
    scope: str,
) -> None:
    connection = RecordingConnection()
    credentials = AzureManagedIdentityCredentials(
        account_name="storage'account",
        client_id=client_id,
        scope=scope,
    )

    credentials.resolve_overrides({}).register(
        cast(DuckDBPyConnection, connection),
        "storage",
    )

    assert connection.queries[:2] == [("INSTALL azure", None), ("LOAD azure", None)]
    query, parameters = connection.queries[-1]
    assert 'TEMPORARY SECRET "storage"' in query
    assert "PROVIDER managed_identity" in query
    assert "ACCOUNT_NAME ?" in query
    assert "storage'account" not in query
    assert "identity'client" not in query
    assert scope not in query
    assert ("CLIENT_ID ?" in query) is (client_id is not None)
    expected = ["storage'account"]
    if client_id is not None:
        expected.append(client_id)
    assert parameters == [*expected, scope]


def test_azure_managed_identity_scope_override_preserves_identity() -> None:
    credentials = AzureManagedIdentityCredentials(
        account_name="storage",
        client_id="identity",
        scope="az://container/",
    )

    resolved = credentials.resolve_overrides({"scope": "az://container/reports/"})

    assert resolved.scope == "az://container/reports/"
    assert credentials.scope == "az://container/"
    assert resolved.account_name == "storage"
    assert resolved.client_id == "identity"


@pytest.mark.parametrize("field", ["account_name", "client_id"])
def test_azure_managed_identity_rejects_blank_identity_fields(field: str) -> None:
    values = {"account_name": "storage", field: " "}
    with pytest.raises(ValueError, match="must not be blank"):
        AzureManagedIdentityCredentials.model_validate(values)


@pytest.mark.parametrize("field", ["account_name", "client_id", "connection_string"])
def test_azure_managed_identity_rejects_identity_overrides(field: str) -> None:
    credentials = AzureManagedIdentityCredentials(account_name="storage")
    with pytest.raises(ValueError, match="Unsupported azure_managed_identity override"):
        credentials.resolve_overrides({field: "replacement"})


def test_azure_managed_identity_requires_scope_before_registration() -> None:
    credentials = AzureManagedIdentityCredentials(account_name="storage")
    connection = RecordingConnection()

    with pytest.raises(ValueError, match="scope is required"):
        credentials.resolve_overrides({})
    with pytest.raises(ValueError, match="scope is required"):
        credentials.register(cast(DuckDBPyConnection, connection), "storage")

    assert connection.queries == []
    assert credentials.resolve_overrides({"scope": "az://container/"}).scope == (
        "az://container/"
    )


def test_azure_rejects_a_blank_connection_string() -> None:
    with pytest.raises(ValueError, match="Connection string must not be blank"):
        AzureConnectionStringCredentials(connection_string=SecretStr(" "))


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ("https://storage.example.test/reports/", "must use an az://"),
        ("az://container/reports", "must end with a trailing slash"),
        ("az:///", "must identify a storage location"),
    ],
)
@pytest.mark.parametrize(
    "credentials",
    [
        AzureConnectionStringCredentials(connection_string=SecretStr("sensitive")),
        AzureManagedIdentityCredentials(account_name="storage"),
    ],
)
def test_azure_rejects_an_invalid_scope(
    scope: str,
    message: str,
    credentials: DuckDBSecret,
) -> None:

    with pytest.raises(ValueError, match=message):
        credentials.resolve_overrides({"scope": scope})


def test_ssh_private_key_scope_override_is_bound() -> None:
    connection = RecordingConnection()
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/sftp-key",
        port=2222,
        scope="sftp://sftp.example.test",
    )

    resolved = credentials.resolve_overrides(
        {"scope": "sftp://sftp.example.test/from_uber/trips/"}
    )
    resolved.register(cast(DuckDBPyConnection, connection), "source_files")

    assert connection.queries[0] == ("INSTALL sshfs FROM community", None)
    assert connection.queries[1] == ("LOAD sshfs", None)
    query, parameters = connection.queries[-1]
    assert "reader" not in query
    assert "/run/secrets/sftp-key" not in query
    assert 'TEMPORARY SECRET "source_files"' in query
    assert parameters == [
        "reader",
        "/run/secrets/sftp-key",
        2222,
        "sftp://sftp.example.test/from_uber/trips/",
    ]


def test_ssh_private_key_uses_the_block_scope_without_an_override() -> None:
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/sftp-key",
        scope="sftp://sftp.example.test",
    )

    assert credentials.resolve_overrides({}).scope == "sftp://sftp.example.test"


def test_ssh_private_key_rejects_a_blank_username() -> None:
    with pytest.raises(ValueError, match="Username must not be blank"):
        SshPrivateKeyCredentials(
            username=SecretStr(" "),
            key_path="/run/secrets/sftp-key",
            scope="sftp://sftp.example.test",
        )


@pytest.mark.parametrize("field", ["username", "key_path", "port"])
def test_ssh_private_key_rejects_connection_detail_overrides(field: str) -> None:
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/sftp-key",
        scope="sftp://sftp.example.test",
    )

    with pytest.raises(ValueError, match="Unsupported ssh_private_key override"):
        credentials.resolve_overrides({field: "must-not-pass"})


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
