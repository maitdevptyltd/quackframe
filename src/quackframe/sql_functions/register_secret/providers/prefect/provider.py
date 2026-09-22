"""Resolve Quackframe credential models from Prefect Block documents."""

from typing import cast

from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringSecret,
    DuckDBSecret,
    MssqlSecret,
    SshPrivateKeySecret,
)
from quackframe.sql_functions.register_secret.providers.prefect.blocks import (
    AzureConnectionStringCredentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)


class PrefectCredentialProvider:
    """Translate Quackframe-owned Prefect Blocks into DuckDB secret models.

    Each supported secret type has an explicit conversion path. Unknown types
    fail clearly instead of falling through to an unrelated Block shape.
    """

    def resolve(self, reference: str, secret_type: str) -> DuckDBSecret:
        """Load a Prefect Block and convert it to the requested DuckDB secret."""

        block_name = self._block_name(reference)
        try:
            if secret_type == "mssql":
                block = cast(MssqlCredentials, MssqlCredentials.load(block_name))
                return MssqlSecret(
                    host=block.host,
                    user=block.user,
                    password=block.password,
                    database=block.database,
                    port=block.port,
                    use_encrypt=block.use_encrypt,
                )

            if secret_type == "azure_connection_string":
                block = cast(
                    AzureConnectionStringCredentials,
                    AzureConnectionStringCredentials.load(block_name),
                )
                return AzureConnectionStringSecret(
                    connection_string=block.connection_string,
                    scope=block.scope,
                )

            if secret_type == "ssh_private_key":
                block = cast(
                    SshPrivateKeyCredentials,
                    SshPrivateKeyCredentials.load(block_name),
                )
                return SshPrivateKeySecret(
                    username=block.username,
                    key_path=block.key_path,
                    port=block.port,
                    scope=block.scope,
                )

        except Exception:  # Prefect exposes several client and validation failures.
            raise RuntimeError(
                f"Prefect credential block '{reference}' could not be loaded. "
                "Confirm that it exists in the configured Prefect API."
            ) from None

        raise ValueError(f"Unsupported Prefect secret type: {secret_type}")

    @staticmethod
    def _block_name(reference: str) -> str:
        """Translate a SQL-friendly reference into a Prefect document name."""

        # Prefect document names require dashes, while Quackframe deliberately
        # limits DuckDB secret aliases to simple SQL identifiers with underscores.
        # Both spellings therefore identify one Prefect document; Prefect cannot
        # store the underscored alternative.
        return reference.replace("_", "-")
