"""Exports through real DuckDB and filesystem clients with controlled remote access."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest
from pydantic import SecretStr

from quackframe import QuackframeConfig, run
from quackframe.credential_loading import loading
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions

pytest.importorskip("adlfs")
from adlfs.spec import AzureBlobFile  # pyright: ignore[reportMissingTypeStubs]
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobProperties
from test_azure_filesystem import key_model
from test_sftp_integration import LoopbackServer

from quackframe.sql_functions.register_filesystem import azure
from quackframe.sql_functions.register_filesystem.adapter import SafeFile
from quackframe.sql_functions.register_filesystem.models import (
    AzureConnectionStringFilesystem,
)


@pytest.fixture
def upload_failures() -> dict[str, bool]:
    return {}


@pytest.fixture
def azure_clients() -> list[azure.OwnedBlobServiceClient]:
    return []


@pytest.fixture
def blob_store(
    monkeypatch: pytest.MonkeyPatch,
    upload_failures: dict[str, bool],
    azure_clients: list[azure.OwnedBlobServiceClient],
) -> dict[str, bytes]:
    """Replace network operations; retain adlfs buffering, staging and finalization."""
    monkeypatch.setattr(AzureBlobFile, "DEFAULT_BLOCK_SIZE", 8192)
    contents: dict[str, bytes] = {}
    modified: dict[str, datetime] = {}
    blocks: dict[tuple[str, str], bytes] = {}

    async def info(self: Any, path: str, **kwargs: Any) -> dict[str, Any]:
        if path in contents:
            return {
                "name": path,
                "type": "file",
                "size": len(contents[path]),
                "last_modified": modified[path],
            }
        if path == "reports" or any(
            name.startswith(path.rstrip("/") + "/") for name in contents
        ):
            return {"name": path, "type": "directory", "size": 0}
        raise FileNotFoundError(path)

    async def listing(self: Any, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        prefix = path.rstrip("/") + "/"
        names = {
            prefix + name[len(prefix) :].split("/")[0]
            for name in contents
            if name.startswith(prefix)
        }
        return [await info(self, name) for name in sorted(names)]

    def container(self: Any, container: str) -> Any:
        if self not in azure_clients:
            azure_clients.append(self)
        name = container
        result = AsyncMock()
        result.__aenter__.return_value = result

        def blob_client(blob: str) -> Any:
            client = AsyncMock()
            client.__aenter__.return_value = client
            path = name + "/" + blob

            async def stage(block_id: str, data: Any, **kwargs: Any) -> None:
                if upload_failures.get("write"):
                    raise PermissionError("protected-upload-token")
                blocks[path, block_id] = bytes(data)

            async def commit(block_list: list[Any], **kwargs: Any) -> dict[str, str]:
                if upload_failures.get("close"):
                    raise PermissionError("protected-upload-token")
                contents[path] = b"".join(
                    blocks[path, block.id] for block in block_list
                )
                modified[path] = datetime.now(UTC)
                return {}

            client.stage_block.side_effect = stage
            client.commit_block_list.side_effect = commit
            return client

        async def download(
            blob: str, offset: int, length: int | None, **kwargs: Any
        ) -> Any:
            data = contents[name + "/" + blob]
            end = None if length is None else offset + length
            return Mock(readall=AsyncMock(return_value=data[offset:end]))

        async def delete(blob: str, **kwargs: Any) -> None:
            del contents[name + "/" + blob]

        def list_blobs(name_starts_with: str = "", **kwargs: Any) -> Any:
            items: list[BlobProperties] = []
            for path, data in contents.items():
                blob = path.removeprefix(name + "/")
                if not path.startswith(name + "/") or not blob.startswith(
                    name_starts_with
                ):
                    continue
                item = BlobProperties(name=blob)
                item.container = name
                item.size = len(data)
                item.metadata = {}
                items.append(item)
            iterator = AsyncMock()
            iterator.__aiter__.return_value = items
            return iterator

        result.list_blobs = Mock(side_effect=list_blobs)
        result.delete_blob.side_effect = delete
        result.get_blob_client = Mock(side_effect=blob_client)
        result.download_blob.side_effect = download
        return result

    def properties_client(self: Any, container: str, blob: str) -> Any:
        result = AsyncMock()
        result.__aenter__.return_value = result
        path = container + "/" + blob

        async def chunks() -> Any:
            yield contents[path]

        async def upload(data: Any, **kwargs: Any) -> None:
            if upload_failures.get("copy"):
                raise PermissionError("protected-copy-token")
            contents[path] = b"".join([chunk async for chunk in data])
            modified[path] = datetime.now(UTC)

        result.download_blob.return_value = Mock(chunks=chunks)
        result.upload_blob.side_effect = upload
        result.exists.return_value = path in contents
        if path in contents:
            properties = BlobProperties(name=blob)
            properties.container = container
            properties.size = len(contents[path])
            properties.metadata = {}
            properties.last_modified = modified[path]
            result.get_blob_properties.return_value = properties
        else:
            result.get_blob_properties.side_effect = ResourceNotFoundError()
        return result

    async def remove(
        self: Any, path: str, recursive: bool = False, **kwargs: Any
    ) -> None:
        for name in list(contents):
            if name == path or (recursive and name.startswith(path.rstrip("/") + "/")):
                del contents[name]

    monkeypatch.setattr(azure.AzureBlobFileSystem, "_info", info)
    monkeypatch.setattr(azure.AzureBlobFileSystem, "_ls", listing)
    monkeypatch.setattr(azure.AzureBlobFileSystem, "_rm", remove)
    monkeypatch.setattr(
        azure.AzureBlobFileSystem, "_container_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(azure.OwnedBlobServiceClient, "get_container_client", container)
    monkeypatch.setattr(
        azure.OwnedBlobServiceClient, "get_blob_client", properties_client
    )
    return contents


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


@pytest.mark.parametrize(
    "strategy", ["sftp", "azure_connection_string", "azure_managed_identity"]
)
@pytest.mark.parametrize("format", ["CSV", "PARQUET"])
@pytest.mark.parametrize("partitioned", [False, True])
@pytest.mark.parametrize("rows", [0, 10000])
def test_all_strategies_export_and_read_back(
    strategy: str,
    format: str,
    partitioned: bool,
    rows: int,
    upload_failures: dict[str, bool],
    blob_store: dict[str, bytes],
    writable_sftp: LoopbackServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolve(reference: str, model_type: Any) -> Any:
        if strategy == "sftp":
            return model_type(
                username="reader",
                key_path=str(tmp_path / "key"),
                port=writable_sftp.port,
                scope="sftp://127.0.0.1",
            )
        return (
            key_model()
            if model_type is AzureConnectionStringFilesystem
            else model_type(account_name="examplestorage", scope="az://reports/")
        )

    monkeypatch.setattr(
        loading, "get_provider", Mock(return_value=Mock(resolve=resolve))
    )
    root = (
        "exports://127.0.0.1"
        if strategy == "sftp"
        else "exports://examplestorage/reports"
    )
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
                [strategy],
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
                upload_failures["write"] = True
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


@pytest.mark.parametrize(
    "strategy", ["azure_connection_string", "azure_managed_identity"]
)
@pytest.mark.parametrize("failure", ["write", "close"])
def test_upload_failure_stops_ordered_execution(
    strategy: str,
    failure: str,
    blob_store: dict[str, bytes],
    upload_failures: dict[str, bool],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = key_model() if strategy == "azure_connection_string" else azure_model()
    monkeypatch.setattr(
        loading,
        "get_provider",
        Mock(return_value=Mock(resolve=Mock(return_value=model))),
    )
    upload_failures[failure] = True
    first, second, third = [
        tmp_path / name for name in ("register.sql", "write.sql", "later.sql")
    ]
    first.write_text(
        f"SELECT quackframe.register_filesystem('example', 'exports', '{strategy}');"
    )
    second.write_text(
        "COPY (SELECT 42 AS value) "
        "TO 'exports://examplestorage/reports/result.csv' (FORMAT CSV);"
    )
    third.write_text("CREATE TABLE should_not_run AS SELECT 1;")
    database = tmp_path / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "database": {"mode": "persistent", "path": database},
            "functions": {"enabled": ["register_filesystem"]},
        }
    )
    with pytest.raises(RuntimeError) as error:
        run([first, second, third], config=config)
    assert "protected-upload-token" not in str(error.value) + caplog.text
    assert "reports/result.csv" not in blob_store
    with duckdb.connect(str(database)) as connection:
        assert connection.execute("SHOW TABLES").fetchall() == []


def azure_model() -> Any:
    from quackframe.sql_functions.register_filesystem.models import (
        AzureManagedIdentityFilesystem,
    )

    return AzureManagedIdentityFilesystem(
        account_name="examplestorage", scope="az://reports/"
    )


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


def test_azure_directory_creation_never_provisions_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        azure.AzureBlobFileSystem, "_container_exists", AsyncMock(return_value=False)
    )
    create = AsyncMock()
    monkeypatch.setattr(azure.OwnedBlobServiceClient, "create_container", create)
    filesystem = key_model().create_filesystem("exports")
    try:
        with pytest.raises(OSError, match="create the directory"):
            filesystem.makedirs("exports://examplestorage/reports/output")
        create.assert_not_awaited()
    finally:
        filesystem.close_backend()


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


def test_azure_move_and_removal_use_literal_paths(
    blob_store: dict[str, bytes],
    upload_failures: dict[str, bool],
) -> None:
    from urllib.parse import quote

    filesystem = key_model().create_filesystem("exports")

    def url(name: str) -> str:
        return "exports://examplestorage/reports/" + quote(name, safe="/")

    try:
        for name in (
            "source?.csv",
            "source1.csv",
            "output?.csv",
            "output1.csv",
            "prefix?/file",
            "prefix1/file",
        ):
            with cast(Any, filesystem).open(url(name), "wb") as file:
                file.write(name.encode())
        upload_failures["copy"] = True
        with pytest.raises(OSError, match="move the path"):
            filesystem.mv(url("source?.csv"), url("output?.csv"))
        assert blob_store["reports/source?.csv"] == b"source?.csv"
        upload_failures.clear()
        filesystem.mv(url("source?.csv"), url("output?.csv"))
        assert blob_store["reports/output?.csv"] == b"source?.csv"
        assert "reports/source?.csv" not in blob_store
        filesystem.rm(url("output?.csv"))
        filesystem.rm(url("prefix?"), recursive=True)
        assert set(blob_store) == {
            "reports/source1.csv",
            "reports/output1.csv",
            "reports/prefix1/file",
        }
    finally:
        filesystem.close_backend()


@pytest.mark.parametrize("runtime", ["direct", "prefect"])
@pytest.mark.parametrize("fail", [False, True])
def test_ordered_export_then_read_in_each_runtime(
    runtime: str,
    fail: bool,
    blob_store: dict[str, bytes],
    upload_failures: dict[str, bool],
    azure_clients: list[azure.OwnedBlobServiceClient],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness: Any = nullcontext()
    if runtime == "prefect":
        pytest.importorskip("prefect")
        from prefect.testing.utilities import prefect_test_harness

        harness = prefect_test_harness()
    monkeypatch.setattr(
        loading,
        "get_provider",
        Mock(return_value=Mock(resolve=Mock(return_value=key_model()))),
    )
    upload_failures["close"] = fail
    first, second, third = [
        tmp_path / name for name in ("register.sql", "export.sql", "read.sql")
    ]
    first.write_text(
        "SELECT quackframe.register_filesystem("
        "'example', 'exports', 'azure_connection_string');"
    )
    second.write_text(
        "COPY (SELECT 42 AS value) "
        "TO 'exports://examplestorage/reports/result.parquet' (FORMAT PARQUET);"
    )
    third.write_text(
        "CREATE TABLE result AS SELECT * FROM read_parquet('exports://examplestorage/reports/result.parquet');"
    )
    database = tmp_path / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": tmp_path,
            "runtime": runtime,
            "database": {"mode": "persistent", "path": database},
            "functions": {"enabled": ["register_filesystem"]},
        }
    )
    with harness:
        if fail:
            with pytest.raises(RuntimeError):
                run([first, second, third], config=config)
        else:
            run([first, second, third], config=config)
    assert azure_clients and all(client.closed for client in azure_clients)
    with duckdb.connect(str(database)) as connection:
        if fail:
            assert connection.execute("SHOW TABLES").fetchall() == []
        else:
            assert connection.execute("SELECT * FROM result").fetchall() == [(42,)]
