"""Shared provider data and the existing secret registration contract."""

from unittest.mock import Mock, patch

import duckdb
import pytest
from pydantic import SecretStr

from quackframe.credential_providers.models import (
    AzureConnectionStringCredentials,
    AzureManagedIdentityCredentials,
    Credentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_secret import function
from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringSecret,
    AzureManagedIdentitySecret,
    DuckDBSecret,
    MssqlSecret,
    SshPrivateKeySecret,
    secret_from_credentials,
)


@pytest.mark.parametrize(
    ("credentials", "secret_class", "secret_type", "override", "field", "expected"),
    [
        (
            MssqlCredentials(
                host="example.test", user=SecretStr("reader"), password=SecretStr("key")
            ),
            MssqlSecret,
            "mssql",
            {"database": "Reporting"},
            "database",
            "Reporting",
        ),
        (
            AzureConnectionStringCredentials(connection_string=SecretStr("key")),
            AzureConnectionStringSecret,
            "azure_connection_string",
            {"scope": "az://container/"},
            "scope",
            "az://container/",
        ),
        (
            AzureManagedIdentityCredentials(account_name="example"),
            AzureManagedIdentitySecret,
            "azure_managed_identity",
            {"scope": "az://container/"},
            "scope",
            "az://container/",
        ),
        (
            SshPrivateKeyCredentials(
                username=SecretStr("reader"), key_path="key", scope="sftp://host/"
            ),
            SshPrivateKeySecret,
            "ssh_private_key",
            {"scope": "sftp://host/reports/"},
            "scope",
            "sftp://host/reports/",
        ),
    ],
)
def test_shared_data_preserves_secret_sql_and_override_behaviour(
    credentials: Credentials,
    secret_class: type[DuckDBSecret],
    secret_type: str,
    override: dict[str, str],
    field: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_values = credentials.model_dump()
    assert not hasattr(credentials, "register")
    assert not hasattr(credentials, "resolve_overrides")
    assert isinstance(secret_from_credentials(credentials), secret_class)
    provider = Mock()
    provider.resolve.return_value = credentials
    monkeypatch.setattr(function, "get_provider", Mock(return_value=provider))

    with (
        patch.object(secret_class, "register", autospec=True) as register,
        duckdb.connect() as connection,
    ):
        install_functions(connection, ("register_secret",))
        assert connection.execute(
            "SELECT quackframe.register_secret(?, ?, ?, overrides := MAP(?, ?))",
            [
                "prefect",
                "shared-block",
                secret_type,
                list(override),
                list(override.values()),
            ],
        ).fetchone() == (True,)

    provider.resolve.assert_called_once_with("shared-block", secret_type)
    registered_secret, _, alias = register.call_args.args
    assert isinstance(registered_secret, secret_class)
    assert getattr(registered_secret, field) == expected
    assert alias == "shared_block"
    assert credentials.model_dump() == original_values
