"""Experimental turn-taking for loopback tests only; never imported by Quackframe."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from threading import RLock, get_ident
from typing import Any, ClassVar, cast

from paramiko import Channel, Message, SFTPAttributes, SFTPClient, SSHClient


class TurnTakingSFTPClient(SFTPClient):
    """Let one worker complete its synchronous exchange before the next starts."""

    observations: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, sock: Channel) -> None:
        self.exchange_lock = RLock()
        self.observation: dict[str, Any] = {
            "requests": 0,
            "contended_requests": 0,
            "threads": set(),
        }
        # Store counters, not clients: diagnostics must not extend client lifetime.
        self.observations.append(self.observation)
        super().__init__(sock)

    def _request(self, command: int, *args: Any) -> tuple[int, Message]:
        waited = not self.exchange_lock.acquire(blocking=False)
        if waited:
            self.exchange_lock.acquire()
        try:
            self.observation["requests"] += 1
            self.observation["contended_requests"] += int(waited)
            self.observation["threads"].add(get_ident())
            # Paramiko does not expose this synchronous hook in its type stubs.
            return cast(
                tuple[int, Message], cast(Any, super())._request(command, *args)
            )
        finally:
            self.exchange_lock.release()

    def listdir_iter(
        self,
        path: str | bytes = ".",
        read_aheads: int = 50,
    ) -> Iterator[SFTPAttributes]:
        # Standard listdir_iter pipelines packets outside _request. Use the
        # ordinary synchronous directory operations so they obey the same lock.
        decoded = path.decode() if isinstance(path, bytes) else path
        return iter(self.listdir_attr(decoded))


def observations() -> list[dict[str, Any]]:
    return [
        {**item, "threads": sorted(item["threads"])}
        for item in TurnTakingSFTPClient.observations
    ]


@contextmanager
def enable_turn_taking() -> Generator[None]:
    """Select the candidate only inside this disposable test process."""
    original = SSHClient.open_sftp

    def open_sftp(self: SSHClient) -> SFTPClient:
        transport = self.get_transport()
        if transport is None:
            raise RuntimeError("Test SSH transport is unavailable")
        ftp = TurnTakingSFTPClient.from_transport(transport)
        if ftp is None:
            raise RuntimeError("Test SFTP channel is unavailable")
        return ftp

    SSHClient.open_sftp = open_sftp
    try:
        yield
    finally:
        SSHClient.open_sftp = original
