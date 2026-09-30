"""Operation-specific filesystem strategies using fsspec backends."""

from abc import abstractmethod
from contextlib import suppress
from typing import ClassVar
from urllib.parse import urlsplit

from duckdb import DuckDBPyConnection

from quackframe.credential_loading.models import (
    CredentialModel,
    SshPrivateKeyCredentials,
)
from quackframe.errors import OptionalDependencyError


class DuckDBFilesystem(CredentialModel):
    """Register a resolved credential's filesystem with the DuckDB instance."""

    filesystem_type: ClassVar[str]

    @abstractmethod
    def register_filesystem_protocol(self, connection: DuckDBPyConnection) -> None:
        """Construct and register one standard filesystem object."""


class SftpFilesystem(SshPrivateKeyCredentials, DuckDBFilesystem):
    """Use shared SSH credentials with serialized SFTP exchanges."""

    filesystem_type: ClassVar[str] = "sftp"

    def register_filesystem_protocol(self, connection: DuckDBPyConnection) -> None:
        """Validate the endpoint, construct the backend, and register its protocols."""

        host = self._endpoint_host()
        try:
            from quackframe.sql_functions.register_filesystem.sftp import (
                SerializedSFTPFileSystem,
            )
        except ImportError:
            raise OptionalDependencyError(
                "The SFTP filesystem requires 'quackframe[sftp]'"
            ) from None

        # Keep the exchange lock and connection local to this registration.
        # Authentication and port come from the Block; scope selects the host.
        try:
            filesystem = SerializedSFTPFileSystem(
                host=host,
                username=self.username.get_secret_value(),
                key_filename=self.key_path,
                port=self.port,
                host_key_fingerprint=self.host_key_fingerprint,
                skip_instance_cache=True,
            )
        except Exception:
            raise RuntimeError(
                "SFTP filesystem could not connect. Check the credential Block, "
                "private-key file, host-key fingerprint and server access."
            ) from None

        try:
            connection.register_filesystem(filesystem)
        except Exception:
            # A rejected registration never transfers ownership to DuckDB.
            # Close the backend's ordinary clients without masking the failure.
            with suppress(Exception):
                filesystem.ftp.close()
            with suppress(Exception):
                filesystem.client.close()
            raise RuntimeError("SFTP filesystem could not be registered") from None

    def _endpoint_host(self) -> str:
        """Reject endpoint authentication or a port that conflicts with the Block."""

        try:
            endpoint = urlsplit(self.scope)
            host = endpoint.hostname
            valid = (
                endpoint.scheme in {"sftp", "ssh"}
                and host
                and not any(character.isspace() for character in host)
                and endpoint.username is None
                and endpoint.password is None
                and endpoint.port in (None, self.port)
                and not endpoint.query
                and not endpoint.fragment
            )
        except ValueError:
            valid = False
            host = None
        if not valid or host is None:
            raise ValueError(
                "SFTP scope must be an sftp:// or ssh:// URI with a host, no "
                "authentication, query or fragment, and no conflicting port"
            )
        return host


FILESYSTEM_MODELS: dict[str, type[DuckDBFilesystem]] = {"sftp": SftpFilesystem}


def get_filesystem_model(filesystem_type: str) -> type[DuckDBFilesystem]:
    """Select one explicitly supported filesystem strategy before loading it."""

    try:
        return FILESYSTEM_MODELS[filesystem_type]
    except KeyError:
        raise ValueError(f"Unsupported filesystem type: {filesystem_type}") from None
