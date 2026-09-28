"""Construct SFTP filesystems using optional fsspec and Paramiko dependencies."""

# fsspec ships no type stubs; keep its untyped boundary inside this adapter.
# pyright: reportMissingTypeStubs=false

from collections.abc import Iterator
from threading import RLock
from typing import Any, cast
from urllib.parse import urlsplit
from weakref import finalize

from fsspec.implementations.sftp import SFTPFileSystem
from paramiko import Channel, Message, SFTPAttributes, SFTPClient, SSHClient

from quackframe.credential_providers.models import SshPrivateKeyCredentials


def _close_clients(ftp: SFTPClient, client: SSHClient) -> None:
    try:
        ftp.close()
    finally:
        client.close()


class SerializedSFTPClient(SFTPClient):
    """Keep DuckDB reader threads from consuming each other's SFTP responses."""

    def __init__(self, sock: Channel) -> None:
        self._request_lock = RLock()
        super().__init__(sock)

    def _request(self, t: int, *args: Any) -> tuple[int, Message]:
        with self._request_lock:
            # Paramiko's synchronous request hook is omitted from its stubs.
            return cast(tuple[int, Message], cast(Any, super())._request(t, *args))

    def listdir_iter(
        self, path: str | bytes = ".", read_aheads: int = 50
    ) -> Iterator[SFTPAttributes]:
        # fsspec uses this iterator. Avoid Paramiko's pipelined variant so
        # listing and file reads use the same serialized request boundary.
        decoded_path = path.decode() if isinstance(path, bytes) else path
        return iter(self.listdir_attr(decoded_path))


class ManagedSFTPFileSystem(SFTPFileSystem):
    """Release the transport when DuckDB releases its filesystem reference."""

    host: str
    ssh_kwargs: dict[str, Any]

    def _connect(self) -> None:
        # Require the execution user's known_hosts rather than silently trusting
        # an unknown server. Authentication uses only the selected block's key.
        self.client = SSHClient()
        try:
            self.client.load_system_host_keys()
            self.client.connect(self.host, **self.ssh_kwargs)
            transport = self.client.get_transport()
            if transport is None:
                raise RuntimeError("SSH transport is unavailable")
            ftp = SerializedSFTPClient.from_transport(transport)
            if ftp is None:
                raise RuntimeError("SFTP channel is unavailable")
            self.ftp = ftp
            channel = self.ftp.get_channel()
            if channel is None:
                raise RuntimeError("SFTP channel is unavailable")
            channel.settimeout(30)
        except Exception:
            self.client.close()
            raise
        self._cleanup = finalize(self, _close_clients, self.ftp, self.client)

    def close(self) -> None:
        """Release transport resources once, including failed registration."""

        self._cleanup()


def create_filesystem(credentials: SshPrivateKeyCredentials) -> ManagedSFTPFileSystem:
    """Validate a Block's endpoint and open an uncached SFTP connection."""

    try:
        scope = urlsplit(credentials.scope)
        valid = (
            scope.scheme in {"sftp", "ssh"}
            and scope.hostname
            and scope.username is None
            and scope.password is None
            and not scope.query
            and not scope.fragment
            and (scope.port is None or scope.port == credentials.port)
        )
    except ValueError:
        raise ValueError("SFTP scope must identify a valid SSH host") from None
    if not valid:
        raise ValueError("SFTP scope must identify an SSH host with a matching port")

    try:
        return ManagedSFTPFileSystem(
            scope.hostname,
            username=credentials.username.get_secret_value(),
            key_filename=credentials.key_path,
            port=credentials.port,
            look_for_keys=False,
            allow_agent=False,
            timeout=30,
            banner_timeout=30,
            auth_timeout=30,
            skip_instance_cache=True,
        )
    except Exception:
        raise RuntimeError(
            "SFTP connection failed; check the block, key file, known_hosts, "
            "and network"
        ) from None
