"""Prefect Block for DuckDB MSSQL credentials."""

from typing import TypeVar

from prefect.blocks.core import Block
from pydantic import Field, SecretStr

from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.models import MssqlCredentials as Credential

T = TypeVar("T", bound=CredentialModel)


class MssqlCredentials(Block):
    """Store reusable SQL Server authentication in Prefect.

    ``database`` may be omitted so reviewed SQL can select it through the
    allowlisted Quackframe override.
    """

    host: str = Field(min_length=1)
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = Field(default=1433, ge=1, le=65535)
    use_encrypt: bool = True
    trust_server_certificate: bool = Field(
        default=False,
        description=(
            "Accept the server certificate without verifying its chain or hostname. "
            "Encryption remains controlled by use_encrypt."
        ),
    )

    def to_credentials(self, model_type: type[T]) -> T:
        """Construct a compatible strategy directly from this Block's fields."""

        if not issubclass(model_type, Credential):
            raise ValueError("Incompatible mssql credential model")
        return model_type(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            use_encrypt=self.use_encrypt,
            trust_server_certificate=self.trust_server_certificate,
        )
