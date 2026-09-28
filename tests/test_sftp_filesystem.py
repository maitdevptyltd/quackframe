"""Exercise real SFTP globbing and DuckDB SQL against a loopback SSH server."""

from __future__ import annotations

import gc
import socket
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any
from unittest.mock import MagicMock, Mock

import duckdb
import pytest
from pydantic import SecretStr

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")

from paramiko import (
    RSAKey,
    ServerInterface,
    SFTPAttributes,
    SFTPHandle,
    SFTPServer,
    SFTPServerInterface,
    SSHClient,
    Transport,
)
from paramiko.common import AUTH_FAILED, AUTH_SUCCESSFUL, OPEN_SUCCEEDED

from quackframe.credential_providers.models import (
    SshPrivateKeyCredentials,
)
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem import function
from quackframe.sql_functions.register_filesystem import sftp as sftp_module
from quackframe.sql_functions.register_filesystem.sftp import (
    create_filesystem,
)


@pytest.fixture
def sftp_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SshPrivateKeyCredentials]:
    root = tmp_path / "remote"
    root.mkdir()
    (root / "a.csv").write_text("value\n1\n")
    (root / "b.csv").write_text("value\n2\n")
    (root / "ignore.txt").write_text("ignored")
    (root / "nested").mkdir()
    (root / "nested/c.csv").write_text("value\n3\n")
    host_key = RSAKey.generate(2048)
    user_key = RSAKey.generate(2048)
    key_path = tmp_path / "client_key"
    user_key.write_private_key_file(str(key_path))

    class Authentication(ServerInterface):
        def check_auth_publickey(self, username: str, key: Any) -> int:
            return (
                AUTH_SUCCESSFUL
                if username == "reader" and key == user_key
                else AUTH_FAILED
            )

        def check_channel_request(self, kind: str, chanid: int) -> int:
            return OPEN_SUCCEEDED

    class Files(SFTPServerInterface):
        def list_folder(self, path: str) -> list[SFTPAttributes]:
            return [
                SFTPAttributes.from_stat(child.stat(), child.name)
                for child in (root / path.lstrip("/")).iterdir()
            ]

        def stat(self, path: str) -> SFTPAttributes | int:
            target = root / path.lstrip("/")
            if not target.exists():
                return 2  # SFTP_NO_SUCH_FILE
            return SFTPAttributes.from_stat(target.stat())

        def open(self, path: str, flags: int, attr: Any) -> SFTPHandle:
            handle = SFTPHandle(flags)
            handle.readfile = (root / path.lstrip("/")).open("rb")  # pyright: ignore[reportAttributeAccessIssue]
            return handle

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(10)
    port = listener.getsockname()[1]
    transports: list[Transport] = []
    errors: list[Exception] = []

    def serve() -> None:
        try:
            client, _ = listener.accept()
            transport = Transport(client)
            transports.append(transport)
            transport.add_server_key(host_key)
            transport.set_subsystem_handler("sftp", SFTPServer, Files)
            transport.start_server(server=Authentication())
        except Exception as error:
            errors.append(error)

    def load_test_host_key(client: SSHClient, filename: str | None = None) -> None:
        client.get_host_keys().add(f"[127.0.0.1]:{port}", "ssh-rsa", host_key)

    monkeypatch.setattr(SSHClient, "load_system_host_keys", load_test_host_key)
    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield SshPrivateKeyCredentials(
            username=SecretStr("reader"),
            key_path=str(key_path),
            port=port,
            scope="sftp://127.0.0.1/",
        )
    finally:
        listener.close()
        for transport in transports:
            transport.close()
        thread.join(timeout=11)
    assert not errors
    assert not thread.is_alive()


def test_sftp_glob_and_recursive_glob(
    sftp_credentials: SshPrivateKeyCredentials,
) -> None:
    filesystem = create_filesystem(sftp_credentials)
    try:
        assert filesystem.glob("/*.csv") == ["/a.csv", "/b.csv"]  # pyright: ignore[reportUnknownMemberType]
        assert filesystem.glob("/**/*.csv") == ["/a.csv", "/b.csv", "/nested/c.csv"]  # pyright: ignore[reportUnknownMemberType]
        assert filesystem.glob("/missing*.csv") == []  # pyright: ignore[reportUnknownMemberType]
    finally:
        filesystem.close()
    assert filesystem.client.get_transport() is None


@pytest.mark.parametrize("persistent", [False, True])
def test_sql_registration_globs_reads_and_closes_sftp(
    sftp_credentials: SshPrivateKeyCredentials,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    persistent: bool,
) -> None:
    provider = Mock()
    provider.resolve.return_value = sftp_credentials
    monkeypatch.setattr(function, "get_provider", Mock(return_value=provider))
    clients: list[SSHClient] = []
    original_connect = SSHClient.connect

    def track_connect(client: SSHClient, *args: Any, **kwargs: Any) -> None:
        clients.append(client)
        original_connect(client, *args, **kwargs)

    monkeypatch.setattr(SSHClient, "connect", track_connect)
    database = str(tmp_path / "test.duckdb") if persistent else ":memory:"
    connection = duckdb.connect(database, config={"threads": 4})
    try:
        install_functions(connection, ("register_secret", "register_filesystem"))
        assert connection.execute(
            "SELECT quackframe.register_filesystem('prefect', 'source_files', 'sftp')"
        ).fetchone() == (True,)
        provider.resolve.assert_called_once_with("source_files", "ssh_private_key")
        assert connection.execute(
            "SELECT value FROM read_csv('sftp:///*.csv') ORDER BY value"
        ).fetchall() == [(1,), (2,)]
        assert connection.execute(
            "SELECT value FROM read_csv('sftp:///**/*.csv') ORDER BY value"
        ).fetchall() == [(1,), (2,), (3,)]
        with pytest.raises(duckdb.InvalidInputException, match="already registered"):
            connection.execute(
                "SELECT quackframe.register_filesystem('prefect', 'other', 'sftp')"
            )
        provider.resolve.assert_called_once()
    finally:
        connection.close()
    gc.collect()
    assert len(clients) == 1
    assert clients[0].get_transport() is None


@pytest.mark.parametrize(
    "scope",
    ["missing-host", "sftp:///path", "sftp://user@host/", "sftp://host:123/"],
)
def test_invalid_scope_fails_before_connecting(scope: str) -> None:
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("reader"), key_path="unused", scope=scope
    )
    with pytest.raises(ValueError, match="SFTP scope"):
        create_filesystem(credentials)


def test_connection_failure_hides_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        SSHClient, "connect", Mock(side_effect=RuntimeError("private credential"))
    )
    close = Mock()
    monkeypatch.setattr(SSHClient, "close", close)
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("private credential"),
        key_path="private credential",
        scope="sftp://example.test/",
    )
    with pytest.raises(RuntimeError) as captured:
        create_filesystem(credentials)
    assert "private credential" not in str(captured.value)
    close.assert_called_once()


def test_failed_registration_closes_the_open_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = SshPrivateKeyCredentials(
        username=SecretStr("reader"), key_path="key", scope="sftp://host/"
    )
    provider = Mock()
    provider.resolve.return_value = credentials
    monkeypatch.setattr(function, "get_provider", Mock(return_value=provider))
    filesystem = Mock()
    monkeypatch.setattr(sftp_module, "create_filesystem", Mock(return_value=filesystem))
    connection = MagicMock()
    duplicate = connection.duplicate.return_value.__enter__.return_value
    duplicate.filesystem_is_registered.return_value = False
    duplicate.register_filesystem.side_effect = RuntimeError("private diagnostic")
    with pytest.raises(RuntimeError) as captured:
        function.register_filesystem(connection, "prefect", "source", "sftp")
    assert "private diagnostic" not in str(captured.value)
    filesystem.close.assert_called_once()
