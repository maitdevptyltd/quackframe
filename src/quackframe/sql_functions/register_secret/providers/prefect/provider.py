"""Resolve Quackframe credential models from Prefect Block documents."""

from typing import cast

from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringCredentials as ResolvedAzureCredentials,
)
from quackframe.sql_functions.register_secret.models import Credential, SecretType
from quackframe.sql_functions.register_secret.models import (
    MssqlCredentials as ResolvedMssqlCredentials,
)
from quackframe.sql_functions.register_secret.providers.prefect.blocks import (
    AzureConnectionStringCredentials,
    MssqlCredentials,
)


class PrefectCredentialProvider:
    """Load the Quackframe-owned Block type selected by the secret strategy."""

    def resolve(self, reference: str, secret_type: SecretType) -> Credential:
        try:
            if secret_type == "mssql":
                block = cast(MssqlCredentials, MssqlCredentials.load(reference))
                return ResolvedMssqlCredentials(
                    host=block.host,
                    user=block.user,
                    password=block.password,
                    database=block.database,
                    port=block.port,
                    use_encrypt=block.use_encrypt,
                )

            block = cast(
                AzureConnectionStringCredentials,
                AzureConnectionStringCredentials.load(reference),
            )
            return ResolvedAzureCredentials(
                connection_string=block.connection_string,
                scope=block.scope,
            )
        except Exception:  # Prefect exposes several client and validation failures.
            raise RuntimeError(
                f"Prefect credential block '{reference}' could not be loaded. "
                "Confirm that it exists in the configured Prefect API."
            ) from None
