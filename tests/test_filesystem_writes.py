"""SFTP exports and shared filesystem errors with controlled remote access."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import duckdb
import pytest
from pydantic import SecretStr

from quackframe.credential_loading import loading
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")
from test_sftp_integration import LoopbackServer

from quackframe.sql_functions.register_filesystem.adapter import SafeFile


@pytest.fixture
def writable_sftp(tmp_path: Path) -> Iterator[LoopbackServer]:
    root = tmp_path / "remote"
    root.mkdir()
    server = LoopbackServer(root)
    server.writable = True
    server.user_key.write_private_key_file(str(tmp_path / "key"))
    server.thread.start()
    try:
        yield server
    finally:
        server.close()


@pytest.mark.parametrize("format", ["CSV", "PARQUET"])
@pytest.mark.parametrize("partitioned", [False, True])
@pytest.mark.parametrize("rows", [0, 10000])
def test_sftp_exports_and_reads_back(
    format: str,
    partitioned: bool,
    rows: int,
    writable_sftp: LoopbackServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolve(reference: str, model_type: Any) -> Any:
        return model_type(
            username="reader",
            key_path=str(tmp_path / "key"),
            port=writable_sftp.port,
            scope="sftp://127.0.0.1",
        )

    monkeypatch.setattr(
        loading, "get_provider", Mock(return_value=Mock(resolve=resolve))
    )
    root = "exports://127.0.0.1"
    path = root + (
        "/nested/output" if partitioned else "/result%20%23." + format.lower()
    )
    options = ", PARTITION_BY (category)" if partitioned else ""
    read_path = path + "/**/*." + format.lower() if partitioned else path
    with duckdb.connect(config={"threads": 4}) as connection:
        with SessionResources(connection) as resources:
            install_functions(connection, ("register_filesystem",), resources)
            connection.execute(
                "SELECT quackframe.register_filesystem('example', 'exports', ?)",
                ["sftp"],
            )
            for iteration in range(3):
                additional = (
                    ("", ", APPEND", ", OVERWRITE")[iteration] if partitioned else ""
                )
                connection.execute(
                    f"COPY (SELECT i + {iteration * 10000} AS i, "
                    f"i % 2 AS category FROM range({rows}) t(i)) "
                    f"TO ? (FORMAT {format}{options}{additional})",
                    [path],
                )
                if partitioned and rows == 0:
                    assert (
                        connection.execute(
                            "SELECT * FROM glob(?)", [read_path]
                        ).fetchall()
                        == []
                    )
                    continue
                copies = 2 if partitioned and iteration == 1 else 1
                assert connection.execute(
                    f"SELECT count(*), sum(i::BIGINT) FROM read_{format.lower()}(?)",
                    [read_path],
                ).fetchone() == (
                    rows * copies,
                    (rows * (rows - 1) // 2 * copies + iteration * rows * 10000)
                    if rows
                    else None,
                )
            if rows and not partitioned:
                writable_sftp.writable = False
                with pytest.raises(duckdb.Error, match="Registered filesystem"):
                    connection.execute(
                        "COPY (SELECT 42) TO ? (FORMAT CSV)", [root + "/denied.csv"]
                    )
                assert connection.execute(
                    f"SELECT count(*) FROM read_{format.lower()}(?)", [read_path]
                ).fetchone() == (rows,)
        assert connection.list_filesystems() == []
    writable_sftp.wait_disconnected()


@pytest.mark.parametrize("operation", ["read", "write", "flush", "commit", "close"])
def test_deferred_errors_never_expose_backend_payloads(operation: str) -> None:
    file = Mock()
    getattr(file, operation).side_effect = PermissionError("protected-query-data-token")
    with pytest.raises(OSError, match="file operation failed") as error:
        getattr(SafeFile(file), operation)(
            b"data"
        ) if operation == "write" else getattr(SafeFile(file), operation)()
    assert "protected" not in str(error.value)
    assert error.value.__suppress_context__


def test_sftp_read_only_account_rejects_writes(
    writable_sftp: LoopbackServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quackframe.sql_functions.register_filesystem.models import SftpFilesystem

    writable_sftp.writable = False
    (writable_sftp.root / "input.csv").write_text("value\n42\n")
    model = SftpFilesystem(
        username=SecretStr("reader"),
        key_path=str(tmp_path / "key"),
        port=writable_sftp.port,
        scope="sftp://127.0.0.1",
    )
    monkeypatch.setattr(
        loading,
        "get_provider",
        Mock(return_value=Mock(resolve=Mock(return_value=model))),
    )
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        install_functions(connection, ("register_filesystem",), resources)
        connection.execute(
            "SELECT quackframe.register_filesystem('example', 'exports', 'sftp')"
        )
        assert connection.execute(
            "SELECT * FROM read_csv('exports://127.0.0.1/input.csv')"
        ).fetchall() == [(42,)]
        with pytest.raises(duckdb.Error, match="could not open"):
            connection.execute(
                "COPY (SELECT 42) TO 'exports://127.0.0.1/denied.csv' (FORMAT CSV)"
            )
    assert not (writable_sftp.root / "denied.csv").exists()
    writable_sftp.wait_disconnected()


def test_sftp_parallel_reads_and_writes_share_the_exchange_lock(
    writable_sftp: LoopbackServer,
    tmp_path: Path,
) -> None:
    from quackframe.sql_functions.register_filesystem.models import SftpFilesystem

    filesystem = SftpFilesystem(
        username=SecretStr("reader"),
        key_path=str(tmp_path / "key"),
        port=writable_sftp.port,
        scope="sftp://127.0.0.1",
    ).create_filesystem("exports")
    payload = b"payload" * 10000

    def round_trip(number: int) -> bytes:
        path = f"exports://127.0.0.1/result-{number}"
        with cast(Any, filesystem).open(path, "wb") as writer:
            assert writer.write(payload) == len(payload)
        with cast(Any, filesystem).open(path, "rb") as reader:
            return reader.read()

    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = [workers.submit(round_trip, number) for number in range(12)]
            assert all(result.result(timeout=15) == payload for result in results)
    finally:
        filesystem.close_backend()
    writable_sftp.wait_disconnected()


def test_sftp_close_acknowledgement_failure_is_not_suppressed() -> None:
    from quackframe.sql_functions.register_filesystem.sftp import SerializedSFTPFile

    file = Mock(closed=False)
    client = Mock()
    from threading import RLock

    client._exchange_lock = RLock()
    client._request.side_effect = PermissionError("protected-close-detail")
    wrapped = SafeFile(SerializedSFTPFile(file, client))
    with pytest.raises(OSError, match="file operation failed") as error:
        wrapped.close()
    assert "protected" not in str(error.value)
    assert file._closed is True
    file.flush.assert_called_once()


def test_file_cleanup_preserves_primary_failure() -> None:
    file = Mock(close=Mock(side_effect=OSError("protected-close")))
    with pytest.raises(ValueError, match="primary"), SafeFile(file):
        raise ValueError("primary")
    file.close.assert_called_once()
