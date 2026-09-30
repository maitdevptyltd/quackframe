"""Shared credential fields, validation and immutable override strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from quackframe.credential_loading.validation import validate_azure_scope


class CredentialModel(BaseModel, ABC):
    """Own credential validation and overrides independently of registration."""

    model_config = ConfigDict(extra="forbid")

    allowed_overrides: ClassVar[frozenset[str]] = frozenset()
    credential_type: ClassVar[str]

    def validate_override_keys(self, overrides: Mapping[str, str]) -> None:
        """Reject fields that this credential type does not explicitly allow."""

        unknown = sorted(set(overrides) - self.allowed_overrides)
        if unknown:
            raise ValueError(
                f"Unsupported {self.credential_type} override field(s): "
                f"{', '.join(unknown)}"
            )

    @abstractmethod
    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        """Return a fully validated credential with safe call-specific changes."""


class MssqlCredentials(CredentialModel):
    """Hold MSSQL credentials and resolve their safe connection overrides.

    Only ``database``, ``port``, and ``use_encrypt`` may be changed by reviewed
    SQL. Authentication fields always come from the selected provider.
    """

    credential_type: ClassVar[str] = "mssql"
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

    @staticmethod
    def _parse_boolean(value: str) -> bool:
        """Parse the SQL values accepted for an encryption override."""

        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ValueError("use_encrypt override must be true or false")


class AzureConnectionStringCredentials(CredentialModel):
    """Hold an Azure connection string and resolve its storage scope.

    Reviewed SQL may choose only the non-sensitive storage ``scope``. The
    connection string always comes from the selected credential provider.
    """

    credential_type: ClassVar[str] = "azure_connection_string"
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


class AzureManagedIdentityCredentials(CredentialModel):
    """Validate Azure storage account, identity selection and scope."""

    credential_type: ClassVar[str] = "azure_managed_identity"
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


class SshPrivateKeyCredentials(CredentialModel):
    """Hold private-key SSH credentials shared by registration strategies.

    Reviewed SQL may replace the credential's remote ``scope``. The username,
    key path, and port always come from the selected provider.
    """

    credential_type: ClassVar[str] = "ssh_private_key"
    allowed_overrides: ClassVar[frozenset[str]] = frozenset({"scope"})

    username: SecretStr
    key_path: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    scope: str = Field(min_length=1)
    host_key_fingerprint: str | None = None

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
