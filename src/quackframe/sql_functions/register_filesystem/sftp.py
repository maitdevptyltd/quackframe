"""SFTP exchanges serialized per connection for DuckDB reads and writes."""

from collections.abc import Iterator
from contextlib import suppress
from hmac import compare_digest
from re import fullmatch
from threading import RLock
from typing import Any, cast

from fsspec.implementations.sftp import (  # pyright: ignore[reportMissingTypeStubs]
    SFTPFileSystem,
)
from paramiko import (
    AutoAddPolicy,
    Channel,
    Message,
    MissingHostKeyPolicy,
    PKey,
    SFTPAttributes,
    SFTPClient,
    SFTPFile,
    SSHClient,
    SSHException,
)
from paramiko.sftp import CMD_CLOSE


class FingerprintPolicy(MissingHostKeyPolicy):
    """Accept only the configured OpenSSH SHA256 server fingerprint."""

    def __init__(self, fingerprint: str) -> None:
        if fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint) is None:
            raise ValueError("Host-key fingerprint must use SHA256 base64 format")
        self.fingerprint = fingerprint

    def missing_host_key(self, client: SSHClient, hostname: str, key: PKey) -> None:
        if not compare_digest(key.fingerprint, self.fingerprint):
            raise SSHException("SFTP host-key fingerprint does not match")


class SerializedSFTPClient(SFTPClient):
    """Keep each synchronous request and its response on the same reader."""

    def __init__(self, sock: Channel) -> None:
        self._exchange_lock = RLock()
        super().__init__(sock)

    def _request(self, command: int, *args: Any) -> tuple[int, Message]:
        # Paramiko protects request IDs, but not the complete exchange. Another
        # reader can otherwise consume this reader's response and leave it waiting.
        with self._exchange_lock:
            return cast(
                tuple[int, Message], cast(Any, super())._request(command, *args)
            )

    def listdir_iter(
        self, path: str | bytes = ".", read_aheads: int = 50
    ) -> Iterator[SFTPAttributes]:
        # Pipelined listing bypasses _request; use synchronous listing so that
        # discovery and file reads share the same exchange lock.
        decoded = path.decode() if isinstance(path, bytes) else path
        return iter(self.listdir_attr(decoded))


class SerializedSFTPFileSystem(SFTPFileSystem):
    """Retain fsspec path and file behavior, selecting a serialized SFTP client."""

    host: str
    ssh_kwargs: dict[str, Any]

    def _open(
        self, path: str, mode: str = "rb", block_size: int | None = None, **kwargs: Any
    ) -> Any:
        file = super()._open(path, mode, block_size, **kwargs)  # pyright: ignore[reportUnknownMemberType]
        return SerializedSFTPFile(file, self.ftp)

    def _connect(self) -> None:
        # Consume our option before forwarding ordinary connection arguments.
        # Paramiko checks the server key before attempting user authentication.
        ssh_kwargs = self.ssh_kwargs.copy()
        fingerprint = ssh_kwargs.pop("host_key_fingerprint", None)
        fingerprint = fingerprint.strip() if fingerprint is not None else ""
        policy = FingerprintPolicy(fingerprint) if fingerprint else AutoAddPolicy()
        client = SSHClient()
        try:
            client.set_missing_host_key_policy(policy)
            client.connect(self.host, **ssh_kwargs)
            transport = client.get_transport()
            if transport is None:
                raise RuntimeError("SFTP transport is unavailable")
            ftp = SerializedSFTPClient.from_transport(transport)
            if ftp is None:
                raise RuntimeError("SFTP channel is unavailable")
        except BaseException:
            with suppress(Exception):
                client.close()
            raise

        # Keep the owned pair intact until its replacement is fully connected.
        previous_ftp = getattr(self, "ftp", None)
        previous_client = getattr(self, "client", None)
        self.client, self.ftp = client, ftp
        try:
            if previous_ftp is not None:
                previous_ftp.close()
        finally:
            if previous_client is not None:
                previous_client.close()


class SerializedSFTPFile:
    """Serialize file exchanges, including writes that bypass client._request."""

    def __init__(self, file: SFTPFile, client: SerializedSFTPClient) -> None:
        self._file = file
        self._client = client

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._file, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            with self._client._exchange_lock:  # pyright: ignore[reportPrivateUsage]
                return attribute(*args, **kwargs)

        return invoke

    def close(self) -> None:
        with self._client._exchange_lock:  # pyright: ignore[reportPrivateUsage]
            if self._file.closed:
                return
            # Paramiko's close suppresses server/transport errors. Export success
            # must include the server's close acknowledgement, so own this step.
            file = cast(Any, self._file)
            try:
                try:
                    file.flush()
                except BaseException:
                    with suppress(Exception):
                        self._client._request(CMD_CLOSE, file.handle)  # pyright: ignore[reportPrivateUsage]
                    raise
                self._client._request(CMD_CLOSE, file.handle)  # pyright: ignore[reportPrivateUsage]
            finally:
                file._closed = True
