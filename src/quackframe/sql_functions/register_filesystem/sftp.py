"""SFTP exchanges serialized per connection for concurrent DuckDB readers."""

from collections.abc import Iterator
from contextlib import suppress
from threading import RLock
from typing import Any, cast

from fsspec.implementations.sftp import (  # pyright: ignore[reportMissingTypeStubs]
    SFTPFileSystem,
)
from paramiko import (
    AutoAddPolicy,
    Channel,
    Message,
    SFTPAttributes,
    SFTPClient,
    SSHClient,
)


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

    def _connect(self) -> None:
        # Match fsspec's connection defaults without patching global SSH behavior.
        self.client = SSHClient()
        self.client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            self.client.connect(self.host, **self.ssh_kwargs)
            transport = self.client.get_transport()
            if transport is None:
                raise RuntimeError("SFTP transport is unavailable")
            ftp = SerializedSFTPClient.from_transport(transport)
            if ftp is None:
                raise RuntimeError("SFTP channel is unavailable")
            self.ftp = ftp
        except BaseException:
            with suppress(Exception):
                self.client.close()
            raise
