"""Provider-independent DuckDB secrets returned by credential providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Self

from duckdb import DuckDBPyConnection
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from quackframe.sql_functions.register_secret.validation import validate_azure_scope


class DuckDBSecret(BaseModel, ABC):
    """Describe a credential that Quackframe can register with DuckDB.

    A credential provider converts stored values into one of these models. The
    SQL function can then apply safe overrides and register the secret without
    checking which kind of credential it received.
    """

    model_config = ConfigDict(extra="forbid")

    allowed_overrides: ClassVar[frozenset[str]] = frozenset()
    secret_type: ClassVar[str]

    def validate_override_keys(self, overrides: Mapping[str, str]) -> None:
        """Reject fields that this secret type does not explicitly allow."""

        unknown = sorted(set(overrides) - self.allowed_overrides)
        if unknown:
            raise ValueError(
                f"Unsupported {self.secret_type} override field(s): "
                f"{', '.join(unknown)}"
            )

    @abstractmethod
    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Return a fully validated secret with safe call-specific changes."""

    @abstractmethod
    def register(self, connection: DuckDBPyConnection, alias: str) -> None:
        """Load required extensions and create one temporary DuckDB secret."""


class MssqlSecret(DuckDBSecret):
    """Hold MSSQL credentials and own their DuckDB registration behaviour.

    Only ``database``, ``port``, and ``use_encrypt`` may be changed by reviewed
    SQL. Authentication fields always come from the selected provider.
    """

    secret_type: ClassVar[str] = "mssql"
    allowed_overrides: ClassVar[frozenset[str]] = frozenset(
        {"database", "port", "use_encrypt"}
    )

    host: str = Field(min_length=1)
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = Field(default=1433, ge=1, le=65535)
    use_encrypt: bool = True

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Parse MSSQL overrides and require a database after merging."""

        self.validate_override_keys(overrides)
        updates: dict[str, object] = {}
        if "database" in overrides:
            updates["database"] = overrides["database"]
        if "port" in overrides:
            try:
                updates["port"] = int(overrides["port"])
            except ValueError:
                raise ValueError("port override must be an integer") from None
        if "use_encrypt" in overrides:
            updates["use_encrypt"] = self._parse_boolean(overrides["use_encrypt"])

        try:
            resolved = self.model_copy(update=updates)
            resolved = type(self).model_validate(resolved.model_dump())
        except ValidationError:
            raise ValueError("MSSQL credential fields are invalid") from None
        if not resolved.database:
            raise ValueError("MSSQL database is required in the block or overrides")
        return resolved

    def register(self, connection: DuckDBPyConnection, alias: str) -> None:
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

    @staticmethod
    def _parse_boolean(value: str) -> bool:
        """Parse the SQL values accepted for an encryption override."""

        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ValueError("use_encrypt override must be true or false")


class AzureConnectionStringSecret(DuckDBSecret):
    """Hold an Azure connection string and own its scoped registration.

    Reviewed SQL may choose only the non-sensitive storage ``scope``. The
    connection string always comes from the selected credential provider.
    """

    secret_type: ClassVar[str] = "azure_connection_string"
    allowed_overrides: ClassVar[frozenset[str]] = frozenset({"scope"})

    connection_string: SecretStr
    scope: str | None = None

    @field_validator("connection_string")
    @classmethod
    def connection_string_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject empty provider values before DuckDB extension work begins."""

        if not value.get_secret_value().strip():
            raise ValueError("Connection string must not be blank")
        return value

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Apply and validate the optional Azure storage scope override."""

        self.validate_override_keys(overrides)
        scope = overrides.get("scope", self.scope)
        if scope is None:
            raise ValueError("Azure scope is required in the block or overrides")
        return self.model_copy(update={"scope": validate_azure_scope(scope)})

    def register(self, connection: DuckDBPyConnection, alias: str) -> None:
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


class AzureManagedIdentitySecret(DuckDBSecret):
    """Register Azure storage access using the execution environment's identity."""

    secret_type: ClassVar[str] = "azure_managed_identity"
    allowed_overrides: ClassVar[frozenset[str]] = frozenset({"scope"})

    account_name: str = Field(min_length=1)
    client_id: str | None = None
    scope: str | None = None

    @field_validator("account_name", "client_id")
    @classmethod
    def identity_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        """Reject blank account or identity values before extension work begins."""

        if value is not None and not value.strip():
            raise ValueError("Azure account name and client ID must not be blank")
        return value

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Apply the storage scope without allowing changes to the identity."""

        self.validate_override_keys(overrides)
        scope = overrides.get("scope", self.scope)
        if scope is None:
            raise ValueError("Azure scope is required in the block or overrides")
        return self.model_copy(update={"scope": validate_azure_scope(scope)})

    def register(self, connection: DuckDBPyConnection, alias: str) -> None:
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


class SshPrivateKeySecret(DuckDBSecret):
    """Hold private-key SSH credentials for DuckDB's ``sshfs`` extension.

    Reviewed SQL may narrow the credential to a remote ``scope``. The username,
    key path, and port always come from the selected provider.
    """

    secret_type: ClassVar[str] = "ssh_private_key"
    allowed_overrides: ClassVar[frozenset[str]] = frozenset({"scope"})

    username: SecretStr
    key_path: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    scope: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject empty provider values before DuckDB extension work begins."""

        if not value.get_secret_value().strip():
            raise ValueError("Username must not be blank")
        return value

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Apply the optional SSH scope override."""

        self.validate_override_keys(overrides)
        scope = overrides.get("scope", self.scope)
        values = self.model_dump()
        values["scope"] = scope
        return type(self).model_validate(values)

    def register(self, connection: DuckDBPyConnection, alias: str) -> None:
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
