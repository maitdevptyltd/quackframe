"""Operation-specific filesystem strategies using fsspec backends."""

from abc import abstractmethod
from contextlib import suppress
from glob import escape
from re import sub
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import quote, unquote, urlsplit

if TYPE_CHECKING:
    from quackframe.sql_functions.register_filesystem.adapter import ProtocolFileSystem

from quackframe.credential_loading.models import (
    AzureConnectionStringCredentials,
    AzureManagedIdentityCredentials,
    CredentialModel,
    SshPrivateKeyCredentials,
)
from quackframe.errors import OptionalDependencyError


class DuckDBFilesystem(CredentialModel):
    """Register a resolved credential's filesystem with the DuckDB instance."""

    filesystem_type: ClassVar[str]
    extra_dependency_bundle: ClassVar[str]

    @abstractmethod
    def create_filesystem(self, protocol: str) -> "ProtocolFileSystem":
        """Construct one independently owned backend with protocol path mapping."""


class SftpFilesystem(SshPrivateKeyCredentials, DuckDBFilesystem):
    """Use shared SSH credentials with serialized SFTP exchanges."""

    filesystem_type: ClassVar[str] = "sftp"
    extra_dependency_bundle: ClassVar[str] = "sftp"

    def create_filesystem(self, protocol: str) -> "ProtocolFileSystem":
        """Connect once and expose validated URLs for this endpoint only."""

        host = self._endpoint_host()
        try:
            from quackframe.sql_functions.register_filesystem.adapter import (
                ProtocolFileSystem,
            )
            from quackframe.sql_functions.register_filesystem.sftp import (
                SerializedSFTPFileSystem,
            )
        except ImportError:
            raise OptionalDependencyError(
                "The SFTP filesystem requires "
                f"'quackframe[{self.extra_dependency_bundle}]'"
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

        def close() -> None:
            try:
                filesystem.ftp.close()
            finally:
                filesystem.client.close()

        authority = f"[{host}]" if ":" in host else host
        if self.port != 22:
            authority = f"{authority}:{self.port}"

        def to_backend(path: str, *, glob_pattern: bool = False) -> str:
            try:
                url = urlsplit(path)
                has_question_mark = "?" in path.partition("#")[0]
                valid = (
                    url.scheme == protocol
                    and url.hostname == host
                    and url.port in (None, self.port)
                    and url.username is None
                    and url.password is None
                    and (not has_question_mark or (glob_pattern and bool(url.path)))
                    and not url.fragment
                )
            except ValueError:
                raise ValueError(
                    "Filesystem URL must match its registered endpoint"
                ) from None
            if not valid:
                raise ValueError("Filesystem URL must match its registered endpoint")
            remote_path = url.path or "/"
            if glob_pattern:
                # URL parsing treats the first raw ? as a query delimiter. In a
                # glob's path it is an operator, including an empty trailing query.
                if has_question_mark:
                    remote_path += "?" + url.query

                # Encoded wildcard characters belong to literal filenames.
                # Escape them before decoding; raw SQL glob operators stay active.
                remote_path = sub(
                    r"%(?:2[aA]|3[fF]|5[bBdD])",
                    lambda match: escape(chr(int(match.group()[1:], 16))),
                    remote_path,
                )
            return unquote(remote_path)

        def from_backend(path: str) -> str:
            return f"{protocol}://{authority}/{quote(path.lstrip('/'), safe='/')}"

        try:
            return ProtocolFileSystem(
                filesystem,
                protocol,
                to_backend,
                from_backend,
                close,
                to_glob=lambda path: to_backend(path, glob_pattern=True),
                skip_instance_cache=True,
            )
        except BaseException:
            with suppress(Exception):
                close()
            raise

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


class AzureConnectionStringFilesystem(
    AzureConnectionStringCredentials, DuckDBFilesystem
):
    """Use the existing Azure connection credential for named Blob reads and writes."""

    filesystem_type: ClassVar[str] = "azure_connection_string"
    extra_dependency_bundle: ClassVar[str] = "azure"

    def create_filesystem(self, protocol: str) -> "ProtocolFileSystem":
        try:
            from quackframe.sql_functions.register_filesystem.azure import (
                connection_account,
                create_azure_filesystem,
            )
        except ImportError:
            raise OptionalDependencyError(
                "The Azure filesystem requires "
                f"'quackframe[{self.extra_dependency_bundle}]'"
            ) from None

        connection_string = self.connection_string.get_secret_value()
        account = connection_account(connection_string)
        return create_azure_filesystem(
            protocol, account, self.scope, connection_string=connection_string
        )


class AzureManagedIdentityFilesystem(AzureManagedIdentityCredentials, DuckDBFilesystem):
    """Use only the selected managed identity for named Blob reads and writes."""

    filesystem_type: ClassVar[str] = "azure_managed_identity"
    extra_dependency_bundle: ClassVar[str] = "azure"

    def create_filesystem(self, protocol: str) -> "ProtocolFileSystem":
        try:
            from quackframe.sql_functions.register_filesystem.azure import (
                create_azure_filesystem,
            )
        except ImportError:
            raise OptionalDependencyError(
                "The Azure filesystem requires "
                f"'quackframe[{self.extra_dependency_bundle}]'"
            ) from None

        return create_azure_filesystem(
            protocol, self.account_name, self.scope, client_id=self.client_id
        )


FILESYSTEM_MODELS: dict[str, type[DuckDBFilesystem]] = {
    "sftp": SftpFilesystem,
    "azure_connection_string": AzureConnectionStringFilesystem,
    "azure_managed_identity": AzureManagedIdentityFilesystem,
}


def get_filesystem_model(filesystem_type: str) -> type[DuckDBFilesystem]:
    """Select one explicitly supported filesystem strategy before loading it."""

    try:
        return FILESYSTEM_MODELS[filesystem_type]
    except KeyError:
        raise ValueError(f"Unsupported filesystem type: {filesystem_type}") from None
