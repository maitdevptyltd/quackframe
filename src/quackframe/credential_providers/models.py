"""Typed credential data independent of DuckDB and filesystem registration."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Credentials(BaseModel):
    """Validated provider data without backend-specific behaviour."""

    model_config = ConfigDict(extra="forbid")


class MssqlCredentials(Credentials):
    """Credential fields for Mssql consumers."""

    host: str = Field(min_length=1)
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = Field(default=1433, ge=1, le=65535)
    use_encrypt: bool = True


class AzureConnectionStringCredentials(Credentials):
    """Credential fields for AzureConnectionString consumers."""

    connection_string: SecretStr
    scope: str | None = None

    @field_validator("connection_string")
    @classmethod
    def connection_string_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject empty provider values before DuckDB extension work begins."""

        if not value.get_secret_value().strip():
            raise ValueError("Connection string must not be blank")
        return value


class AzureManagedIdentityCredentials(Credentials):
    """Credential fields for AzureManagedIdentity consumers."""

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


class SshPrivateKeyCredentials(Credentials):
    """Credential fields for SshPrivateKey consumers."""

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
