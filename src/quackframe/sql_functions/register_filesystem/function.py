"""Load shared credentials and register a filesystem on the DuckDB instance."""

from duckdb import DuckDBPyConnection

from quackframe.credential_providers.models import SshPrivateKeyCredentials
from quackframe.credential_providers.registry import get_provider
from quackframe.errors import OptionalDependencyError


def register_filesystem(
    connection: DuckDBPyConnection,
    provider: str,
    reference: str,
    filesystem_type: str,
) -> bool:
    """Register one SFTP endpoint using the referenced private-key credentials."""

    if filesystem_type != "sftp":
        raise ValueError(
            "Unsupported filesystem type; currently only sftp is supported"
        )

    try:
        from quackframe.sql_functions.register_filesystem.sftp import create_filesystem
    except ModuleNotFoundError as error:
        if error.name in {"fsspec", "paramiko"}:
            raise OptionalDependencyError(
                "SFTP filesystem registration requires 'quackframe[sftp]'"
            ) from None
        raise

    # A duplicate reaches the same database instance without re-entering the
    # connection executing this UDF. Registration is immediate for later SQL.
    with connection.duplicate() as filesystem_connection:
        if any(
            filesystem_connection.filesystem_is_registered(protocol)
            for protocol in ("sftp", "ssh")
        ):
            raise ValueError("An SFTP or SSH filesystem is already registered")

        credentials = get_provider(provider).resolve(reference, "ssh_private_key")
        if not isinstance(credentials, SshPrivateKeyCredentials):
            raise ValueError("SFTP requires SSH private-key credentials")
        filesystem = create_filesystem(credentials)
        try:
            filesystem_connection.register_filesystem(filesystem)
        except Exception:
            filesystem.close()
            raise RuntimeError("SFTP filesystem could not be registered") from None
    return True
