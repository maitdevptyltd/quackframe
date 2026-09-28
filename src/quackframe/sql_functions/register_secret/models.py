"""Specialised DuckDB secret registration strategies."""

from abc import abstractmethod
from typing import ClassVar

from duckdb import DuckDBPyConnection

from quackframe.credential_loading import models as credentials


class DuckDBSecret(credentials.CredentialModel):
    """Register a resolved credential as one temporary DuckDB secret."""

    secret_type: ClassVar[str]

    @abstractmethod
    def register_duckdb_secret(
        self, connection: DuckDBPyConnection, alias: str
    ) -> None:
        """Load required extensions and register parameter-bound credentials."""


class MssqlSecret(credentials.MssqlCredentials, DuckDBSecret):
    """Register MssqlCredentials as a temporary DuckDB secret."""

    secret_type: ClassVar[str] = "mssql"

    def register_duckdb_secret(
        self, connection: DuckDBPyConnection, alias: str
    ) -> None:
        """Create a temporary MSSQL secret using bound credential values."""

        if not self.database:
            raise ValueError("MSSQL database is required before registration")

        connection.execute("INSTALL mssql FROM community")
        connection.execute("LOAD mssql")
        # The checked alias is the only value written into the SQL text. Every
        # credential value stays in bound parameters and out of error messages.
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
                self.host,
                self.port,
                self.database,
                self.user.get_secret_value(),
                self.password.get_secret_value(),
                self.use_encrypt,
            ],
        )


class AzureConnectionStringSecret(
    credentials.AzureConnectionStringCredentials, DuckDBSecret
):
    """Register AzureConnectionStringCredentials as a temporary DuckDB secret."""

    secret_type: ClassVar[str] = "azure_connection_string"

    def register_duckdb_secret(
        self, connection: DuckDBPyConnection, alias: str
    ) -> None:
        """Create a scoped temporary Azure secret using bound values."""

        if self.scope is None:
            raise ValueError("Azure scope is required before registration")

        connection.execute("INSTALL azure")
        connection.execute("LOAD azure")
        # Secret material remains in the parameter payload rather than the SQL
        # string, which keeps it out of generated SQL and parser diagnostics.
        connection.execute(
            f'''
            CREATE OR REPLACE TEMPORARY SECRET "{alias}" (
                TYPE azure,
                PROVIDER config,
                CONNECTION_STRING ?,
                SCOPE ?
            )
            ''',
            [self.connection_string.get_secret_value(), self.scope],
        )


class AzureManagedIdentitySecret(
    credentials.AzureManagedIdentityCredentials, DuckDBSecret
):
    """Register AzureManagedIdentityCredentials as a temporary DuckDB secret."""

    secret_type: ClassVar[str] = "azure_managed_identity"

    def register_duckdb_secret(
        self, connection: DuckDBPyConnection, alias: str
    ) -> None:
        """Create a scoped temporary Azure managed-identity secret."""

        if self.scope is None:
            raise ValueError("Azure scope is required before registration")

        connection.execute("INSTALL azure")
        connection.execute("LOAD azure")
        # Omit CLIENT_ID entirely to let Azure select the available identity.
        # Account, identity, and scope values always remain bound parameters.
        client_id_option = ""
        parameters = [self.account_name]
        if self.client_id is not None:
            client_id_option = "CLIENT_ID ?,"
            parameters.append(self.client_id)
        parameters.append(self.scope)
        connection.execute(
            f'''
            CREATE OR REPLACE TEMPORARY SECRET "{alias}" (
                TYPE azure,
                PROVIDER managed_identity,
                ACCOUNT_NAME ?,
                {client_id_option}
                SCOPE ?
            )
            ''',
            parameters,
        )


class SshPrivateKeySecret(credentials.SshPrivateKeyCredentials, DuckDBSecret):
    """Register SshPrivateKeyCredentials as a temporary DuckDB secret."""

    secret_type: ClassVar[str] = "ssh_private_key"

    def register_duckdb_secret(
        self, connection: DuckDBPyConnection, alias: str
    ) -> None:
        """Create a temporary SSH secret using bound credential values."""

        connection.execute("INSTALL sshfs FROM community")
        connection.execute("LOAD sshfs")
        # The checked alias is the only value written into the SQL text. Every
        # credential value stays in bound parameters and out of error messages.
        connection.execute(
            f'''
            CREATE OR REPLACE TEMPORARY SECRET "{alias}" (
                TYPE SSH,
                USERNAME ?,
                KEY_PATH ?,
                PORT ?,
                SCOPE ?
            )
            ''',
            [
                self.username.get_secret_value(),
                self.key_path,
                self.port,
                self.scope,
            ],
        )


MssqlCredentials = MssqlSecret
AzureConnectionStringCredentials = AzureConnectionStringSecret
AzureManagedIdentityCredentials = AzureManagedIdentitySecret
SshPrivateKeyCredentials = SshPrivateKeySecret


SECRET_MODELS: dict[str, type[DuckDBSecret]] = {
    model.secret_type: model
    for model in (
        MssqlSecret,
        AzureConnectionStringSecret,
        AzureManagedIdentitySecret,
        SshPrivateKeySecret,
    )
}


def get_secret_model(secret_type: str) -> type[DuckDBSecret]:
    """Select one explicitly supported secret strategy before loading it."""

    try:
        return SECRET_MODELS[secret_type]
    except KeyError:
        raise ValueError(f"Unsupported secret type: {secret_type}") from None
