"""Azure strategy isolation, named DuckDB reads and resource lifetime."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import duckdb
import pytest
from pydantic import SecretStr

from quackframe import ExecutionError, QuackframeConfig, run
from quackframe.credential_loading import loading
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem.models import (
    AzureConnectionStringFilesystem,
    AzureManagedIdentityFilesystem,
)

pytest.importorskip("adlfs")
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobProperties

from quackframe.sql_functions.register_filesystem import azure
from quackframe.sql_functions.register_filesystem.adapter import SafeFile

CONNECTION = (
    "DefaultEndpointsProtocol=https;AccountName=examplestorage;"
    "AccountKey=YWJjZA==;EndpointSuffix=core.windows.net"
)


def key_model(scope: str = "az://reports/") -> AzureConnectionStringFilesystem:
    return AzureConnectionStringFilesystem(
        connection_string=SecretStr(CONNECTION), scope=scope
    )


@pytest.mark.parametrize("key", ["AccountKey", "SharedAccessSignature"])
@pytest.mark.parametrize("padding", [" {}", "{} ", "\t{}"])
def test_padded_credential_keys_fail_before_sdk_construction(
    key: str,
    padding: str,
) -> None:
    connection = CONNECTION.replace("AccountKey=", padding.format(key) + "=")
    model = AzureConnectionStringFilesystem(
        connection_string=SecretStr(connection), scope="az://reports/"
    )
    with patch.object(
        azure.OwnedBlobServiceClient, "from_connection_string"
    ) as factory:
        with pytest.raises(ValueError, match="connection string"):
            model.create_filesystem("reports-key")
        factory.assert_not_called()


@pytest.mark.parametrize("strategy", ["key", "identity"])
def test_closed_backends_are_collectible(strategy: str) -> None:
    references: list[weakref.ReferenceType[Any]] = []
    unrelated = Mock()
    unrelated_callback = Mock()
    unrelated_finalizer = weakref.finalize(unrelated, unrelated_callback)
    try:
        for number in range(5):
            model = (
                key_model()
                if strategy == "key"
                else AzureManagedIdentityFilesystem(
                    account_name="examplestorage", scope="az://reports/"
                )
            )
            filesystem = model.create_filesystem(f"reports-{number}")
            references.append(weakref.ref(filesystem.backend))
            references.append(weakref.ref(filesystem.backend.service_client))
            filesystem.close_backend()
            del filesystem
        gc.collect()
        assert all(reference() is None for reference in references)
        assert unrelated_finalizer.alive
        unrelated_callback.assert_not_called()
    finally:
        unrelated_finalizer.detach()


def test_failed_backend_initialization_releases_inherited_finalizer() -> None:
    references: list[weakref.ReferenceType[Any]] = []

    def retain_backend(retained: object) -> None:
        pass

    def fail_after_finalizer(self: Any, **kwargs: Any) -> None:
        references.append(weakref.ref(self))
        weakref.finalize(self, retain_backend, self)
        raise ValueError("protected-construction-detail")

    with (
        patch.object(azure.AzureBlobFileSystem, "__init__", fail_after_finalizer),
        patch.object(azure.BlobServiceClient, "close", new_callable=AsyncMock) as close,
    ):
        with pytest.raises(RuntimeError, match="could not be created"):
            key_model().create_filesystem("reports-key")
        close.assert_awaited_once()
    gc.collect()
    assert references and all(reference() is None for reference in references)


@pytest.mark.parametrize("client_id", [None, "selected-identity"])
def test_identity_is_explicit_and_cleanup_is_idempotent(client_id: str | None) -> None:
    identity = Mock(close=AsyncMock())
    with (
        patch.object(
            azure, "ManagedIdentityCredential", return_value=identity
        ) as factory,
        patch.object(azure.BlobServiceClient, "close", new_callable=AsyncMock) as close,
    ):
        model = AzureManagedIdentityFilesystem(
            account_name="examplestorage", client_id=client_id, scope="az://reports/"
        )
        filesystem = model.create_filesystem("reports-mi")
        factory.assert_called_once_with(
            client_id=client_id, _exclude_workload_identity_credential=True
        )
        filesystem.close_backend()
        filesystem.close_backend()
        close.assert_awaited_once()
        identity.close.assert_awaited_once()


@pytest.mark.parametrize("strategy", ["key", "identity"])
def test_ambient_credentials_cannot_replace_selected_client(
    monkeypatch: pytest.MonkeyPatch, strategy: str
) -> None:
    for name in (
        "ACCOUNT_NAME",
        "ACCOUNT_KEY",
        "CONNECTION_STRING",
        "SAS_TOKEN",
        "CLIENT_ID",
        "CLIENT_SECRET",
        "TENANT_ID",
        "ANON",
    ):
        monkeypatch.setenv("AZURE_STORAGE_" + name, "unrelated-protected-value")
    model = (
        key_model()
        if strategy == "key"
        else AzureManagedIdentityFilesystem(
            account_name="examplestorage", scope="az://reports/"
        )
    )
    with (
        patch.object(
            azure.AzureBlobFileSystem, "_get_default_azure_credential"
        ) as default,
        patch.object(
            azure.AzureBlobFileSystem, "_get_credential_from_service_principal"
        ) as principal,
    ):
        filesystem = model.create_filesystem("reports-files")
        try:
            backend = filesystem.backend
            assert backend.service_client.account_name == "examplestorage"
            assert (
                backend.service_client.url
                == "https://examplestorage.blob.core.windows.net/"
            )
            assert backend.connection_string is None
            assert backend.account_key is None
            assert backend.sas_token is None
            default.assert_not_called()
            principal.assert_not_called()
        finally:
            filesystem.close_backend()


@pytest.mark.parametrize(
    "scope",
    [
        "az://reports/",
        "azure://reports/folder/",
        "abfss://reports@examplestorage.dfs.core.windows.net/folder/",
    ],
)
def test_scope_does_not_prepend_a_root_or_restrict_containers(scope: str) -> None:
    filesystem = key_model(scope).create_filesystem("reports-key")
    try:
        assert (
            filesystem.to_backend("reports-key://another/full/name.csv")
            == "another/full/name.csv"
        )
    finally:
        filesystem.close_backend()


@pytest.mark.parametrize(
    "scope",
    [
        None,
        "az://reports",
        "az://bad--container/",
        "az://user@reports/",
        "az://reports/?secret=protected",
        "az://reports/#fragment",
        "abfss://reports@otheraccount.dfs.core.windows.net/",
        "abfss://reports@examplestorage.dfs.core.windows.net:0/",
        "https://examplestorage.blob.core.windows.net/reports/",
    ],
)
def test_invalid_scope_fails_before_client_creation(scope: str | None) -> None:
    with patch.object(azure, "OwnedBlobServiceClient") as client:
        with pytest.raises(ValueError, match="scope"):
            azure.create_azure_filesystem("reports-files", "examplestorage", scope)
        client.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        "protected",
        CONNECTION + ";AccountName=another",
        CONNECTION.replace("https", "http"),
        CONNECTION.replace("core.windows.net", "core.chinacloudapi.cn"),
        CONNECTION + ";BlobEndpoint=https://otheraccount.blob.core.windows.net",
        CONNECTION + ";SharedAccessSignature=protected",
        "AccountName=examplestorage",
    ],
)
def test_unsupported_connection_strings_are_sanitized(value: str) -> None:
    with pytest.raises(ValueError) as error:
        azure.connection_account(value)
    assert "protected" not in str(error.value)
    assert "YWJjZA" not in str(error.value)


def test_sas_connection_string_account() -> None:
    assert (
        azure.connection_account(
            "AccountName=examplestorage;SharedAccessSignature=sv=2025-01-05&sig=protected"
        )
        == "examplestorage"
    )


@pytest.mark.parametrize("sas", [False, True])
@pytest.mark.parametrize("trailing_slash", ["", "/"])
def test_standard_service_endpoints_reach_sdk(sas: bool, trailing_slash: str) -> None:
    endpoints = ";".join(
        f"{service.title()}Endpoint=https://examplestorage.{service}.core.windows.net"
        f"{trailing_slash}"
        for service in ("blob", "queue", "table", "file")
    )
    connection = (
        ("SharedAccessSignature=sv=2025-01-05&sig=protected" if sas else CONNECTION)
        + ";"
        + endpoints
        + ";"
    )
    assert azure.connection_account(connection) == "examplestorage"
    # Real SDK construction is offline and verifies the unmodified string's
    # endpoint and authentication interpretation, not just our own parser.
    client = azure.OwnedBlobServiceClient.from_connection_string(connection)
    try:
        assert client.account_name == "examplestorage"
        assert (
            client.primary_endpoint.split("?", 1)[0]
            == "https://examplestorage.blob.core.windows.net/"
        )
        assert client.credential is not None or "sig=protected" in client.url
    finally:
        azure.sync(azure.get_loop(), client.close)


@pytest.mark.parametrize(
    ("connection", "reason"),
    [
        ("sensitive", "entry 1 must have the form name=value"),
        (CONNECTION + "; sensitive=x", "whitespace around its field name"),
        (CONNECTION + ";sensitive=x", "unsupported field name"),
        (CONNECTION + ";AccountKey=sensitive", "repeats a field name"),
        (CONNECTION.replace("YWJjZA==", " "), "empty value"),
        (CONNECTION.replace("https", "http"), "DefaultEndpointsProtocol"),
        (CONNECTION.replace("core.windows.net", "sensitive"), "EndpointSuffix"),
        ("AccountName=examplestorage", "exactly one"),
        ("AccountKey=sensitive", "supply AccountName"),
        (CONNECTION.replace("examplestorage", "INVALID"), "3-24"),
        (CONNECTION + ";BlobEndpoint=https://sensitive", "BlobEndpoint"),
        (CONNECTION + ";QueueEndpoint=https://sensitive", "QueueEndpoint"),
        (CONNECTION + ";TableEndpoint=https://sensitive", "TableEndpoint"),
        (CONNECTION + ";FileEndpoint=https://sensitive", "FileEndpoint"),
    ],
)
def test_connection_errors_explain_rejection_without_values(
    connection: str,
    reason: str,
) -> None:
    model = AzureConnectionStringFilesystem(
        connection_string=SecretStr(connection), scope="az://reports/"
    )
    with patch.object(
        azure.OwnedBlobServiceClient, "from_connection_string"
    ) as factory:
        with pytest.raises(ValueError, match=reason) as error:
            model.create_filesystem("reports-key")
        factory.assert_not_called()
    assert "sensitive" not in str(error.value)
    assert "YWJjZA" not in str(error.value)
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    "path",
    [
        "reports-files://bad--container/file.csv",
        "reports-files://user@reports/file.csv",
        "reports-files://reports:443/file.csv",
        "reports-files://reports/file.csv?sig=protected",
        "reports-files://reports/file.csv#fragment",
        "reports-files:///file.csv",
        "reports-files://reports%2fanother/file.csv",
        "reports-files://Reports/file.csv",
        "reports-files://reports.blob.core.windows.net/file.csv",
        "other-files://reports/file.csv",
    ],
)
def test_read_urls_cannot_redirect_the_backend(path: str) -> None:
    to_backend, _, _ = azure.azure_paths("reports-files")
    with pytest.raises(ValueError):
        to_backend(path)


@pytest.mark.parametrize(
    "name",
    [
        "reports/space name.csv",
        "reports/100%.csv",
        "reports/report#1?.csv",
        "reports/é.csv",
        "reports/literal*.csv",
        "reports/literal[1].csv",
        "reports/double//slash.csv",
        "reports/Upper.CSV",
        "reports/literal%2F.csv",
        "reports/account=example/file_date=2026-09-16/data.csv",
        "reports/literal%3D.csv",
        "$web/index.html",
    ],
)
def test_discovery_paths_round_trip_without_normalization(name: str) -> None:
    to_backend, from_backend, _ = azure.azure_paths("reports-files")
    assert from_backend(name) == "reports-files://" + azure.quote(name, safe="/=")
    assert to_backend(from_backend(name)) == name


def test_encoded_wildcards_stay_literal_in_globs() -> None:
    _, _, to_glob = azure.azure_paths("reports-files")
    assert to_glob("reports-files://reports/a%2A*.csv") == "reports/a[*]*.csv"


def test_partial_backend_construction_closes_client() -> None:
    with (
        patch.object(
            azure, "ExplicitAzureFileSystem", side_effect=ValueError("protected")
        ),
        patch.object(azure.BlobServiceClient, "close", new_callable=AsyncMock) as close,
    ):
        with pytest.raises(RuntimeError, match="could not be created") as error:
            key_model().create_filesystem("reports-key")
        assert "protected" not in str(error.value)
        close.assert_awaited_once()


def test_client_construction_failure_closes_identity() -> None:
    identity = Mock(close=AsyncMock())
    with (
        patch.object(azure, "ManagedIdentityCredential", return_value=identity),
        patch.object(
            azure, "OwnedBlobServiceClient", side_effect=ValueError("protected")
        ),
    ):
        with pytest.raises(RuntimeError, match="could not be created"):
            azure.create_azure_filesystem(
                "reports-mi", "examplestorage", "az://reports/"
            )
        identity.close.assert_awaited_once()


def test_deferred_file_errors_are_sanitized() -> None:
    reader = Mock(read=Mock(side_effect=RuntimeError("protected-token")))
    wrapped = SafeFile(reader)
    with pytest.raises(OSError, match="file operation failed") as error:
        wrapped.read()
    assert "protected" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.fixture
def azure_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[list[azure.OwnedBlobServiceClient]]:
    """Keep real adlfs/DuckDB operations; replace remote metadata and downloads."""
    clients: list[azure.OwnedBlobServiceClient] = []
    content = b"value\n42\n"
    names = ["reports/first.csv", "reports/special #?.csv", "reports/literal*.csv"]
    parquet = tmp_path / "data.parquet"
    with duckdb.connect() as connection:
        connection.execute(
            "COPY (SELECT 42 AS value) TO ? (FORMAT PARQUET)", [str(parquet)]
        )
    contents = dict.fromkeys(names, content)
    contents["reports/data.parquet"] = parquet.read_bytes()
    names = list(contents)

    async def info(self: Any, path: str, **kwargs: Any) -> dict[str, Any]:
        if path not in names:
            return {"name": path, "type": "directory", "size": 0}
        return {
            "name": path,
            "type": "file",
            "size": len(contents[path]),
            "last_modified": datetime(2026, 1, 1, tzinfo=UTC),
        }

    async def listing(self: Any, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [await info(self, name) for name in names]

    def container(self: azure.OwnedBlobServiceClient, *args: Any, **kwargs: Any) -> Any:
        if self not in clients:
            clients.append(self)
        result = AsyncMock()
        result.__aenter__.return_value = result
        blobs = AsyncMock()
        properties: list[BlobProperties] = []
        for name in names:
            item = BlobProperties(name=name.removeprefix("reports/"))
            item.container = "reports"
            item.size = len(contents[name])
            properties.append(item)
        blobs.__aiter__.return_value = properties
        result.list_blobs = Mock(return_value=blobs)

        async def download(
            blob: str, offset: int, length: int | None, **options: Any
        ) -> Any:
            data = contents["reports/" + blob]
            end = None if length is None else offset + length
            return Mock(readall=AsyncMock(return_value=data[offset:end]))

        result.download_blob.side_effect = download
        return result

    def blob_client(
        self: azure.OwnedBlobServiceClient, container: str, blob: str
    ) -> Any:
        result = AsyncMock()
        result.__aenter__.return_value = result
        exists = f"{container}/{blob}" in names
        result.exists.return_value = exists
        if exists:
            item = BlobProperties(name=blob)
            item.container = container
            item.size = len(contents[f"{container}/{blob}"])
            item.metadata = {}
            result.get_blob_properties.return_value = item
        else:
            result.get_blob_properties.side_effect = ResourceNotFoundError()
        return result

    monkeypatch.setattr(azure.AzureBlobFileSystem, "_info", info)
    monkeypatch.setattr(azure.AzureBlobFileSystem, "_ls", listing)
    monkeypatch.setattr(azure.OwnedBlobServiceClient, "get_container_client", container)
    monkeypatch.setattr(azure.OwnedBlobServiceClient, "get_blob_client", blob_client)
    yield clients


@pytest.mark.parametrize("threads", [1, 4])
def test_both_strategies_read_through_real_duckdb_and_adlfs(
    azure_data: list[azure.OwnedBlobServiceClient],
    monkeypatch: pytest.MonkeyPatch,
    threads: int,
) -> None:
    provider = Mock()

    def resolve(reference: str, model_type: type[Any]) -> Any:
        return (
            key_model()
            if model_type is AzureConnectionStringFilesystem
            else AzureManagedIdentityFilesystem(
                account_name="examplestorage", scope="az://reports/"
            )
        )

    provider.resolve.side_effect = resolve
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    with duckdb.connect(config={"threads": threads}) as connection:
        with SessionResources(connection) as resources:
            install_functions(connection, ("register_filesystem",), resources)
            for kind, protocol in [
                ("azure_connection_string", "reports-key"),
                ("azure_managed_identity", "reports-mi"),
            ]:
                assert connection.execute(
                    "SELECT quackframe.register_filesystem('example', ?, ?, ?)",
                    [protocol, kind, protocol],
                ).fetchone() == (True,)
                paths = connection.execute(
                    "SELECT file FROM glob(?)",
                    [f"{protocol}://reports/*.csv"],
                ).fetchall()
                assert len(paths) == 3
                assert any("%23%3F" in row[0] for row in paths)
                rows = connection.execute(
                    "SELECT value, filename FROM read_csv(?, filename=true)",
                    [[row[0] for row in paths]],
                ).fetchall()
                assert len(rows) == 3
                assert all(
                    row[0] == 42 and row[1].startswith(protocol + "://") for row in rows
                )
                assert connection.execute(
                    "SELECT content FROM read_blob(?)", [paths[0][0]]
                ).fetchone() == (b"value\n42\n",)
                assert connection.execute(
                    "SELECT value FROM read_parquet(?)",
                    [f"{protocol}://reports/data.parquet"],
                ).fetchone() == (42,)
            assert len(azure_data) == 2
            assert all(not client.closed for client in azure_data)
        assert all(client.closed for client in azure_data)


def test_safe_reader_preserves_seek_and_context_manager() -> None:
    original = BytesIO(b"abcdef")
    with SafeFile(original) as reader:
        assert reader.read(2) == b"ab"
        reader.seek(4)
        assert reader.read() == b"ef"
    assert original.closed


def test_accounts_and_backend_lifetimes_are_independent() -> None:
    first = key_model().create_filesystem("first-account")
    second = AzureConnectionStringFilesystem(
        connection_string=SecretStr(
            CONNECTION.replace("examplestorage", "otherstorage")
        ),
        scope="az://reports/",
    ).create_filesystem("second-account")
    try:
        assert first.backend is not second.backend
        assert first.backend.service_client.account_name == "examplestorage"
        assert second.backend.service_client.account_name == "otherstorage"
        first.close_backend()
        assert not second.backend.service_client.closed
        assert (
            first.to_backend("first-account://reports/file.csv") == "reports/file.csv"
        )
        assert (
            second.to_backend("second-account://reports/file.csv") == "reports/file.csv"
        )
        assert (
            second.to_backend("second-account://another/file.csv") == "another/file.csv"
        )
        # A URL cannot select an account: its authority is always a container.
        assert (
            second.to_backend("second-account://examplestorage/reports/file.csv")
            == "examplestorage/reports/file.csv"
        )
        assert second.backend.service_client.account_name == "otherstorage"
    finally:
        first.close_backend()
        second.close_backend()


def test_managed_identity_does_not_select_federated_workload_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("IDENTITY_ENDPOINT", "MSI_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_TENANT_ID", "unrelated-tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "unrelated-client")
    monkeypatch.setenv("AZURE_FEDERATED_TOKEN_FILE", "unrelated-token-file")
    monkeypatch.setenv("AZURE_AUTHORITY_HOST", "https://login.microsoftonline.com")
    with patch(
        "azure.identity.aio._credentials.workload_identity.WorkloadIdentityCredential",
        side_effect=AssertionError("Workload identity must not be selected"),
    ) as workload:
        filesystem = AzureManagedIdentityFilesystem(
            account_name="examplestorage", scope="az://reports/"
        ).create_filesystem("reports-mi")
        filesystem.close_backend()
        workload.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_ordered_azure_files_close_clients_after_success_or_sql_failure(
    azure_data: list[azure.OwnedBlobServiceClient],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fail: bool,
) -> None:
    provider = Mock(resolve=Mock(return_value=key_model()))
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    first = tmp_path / "register.sql"
    first.write_text(
        "SELECT quackframe.register_filesystem('example', 'reports-key', "
        "'azure_connection_string');",
        encoding="utf-8",
    )
    second = tmp_path / "read.sql"
    second.write_text(
        "CREATE TABLE result AS SELECT * FROM read_csv("
        "'reports-key://reports/first.csv');"
        + ("SELECT error('deliberate');" if fail else ""),
        encoding="utf-8",
    )
    database = tmp_path / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "database": {"mode": "persistent", "path": database},
            "functions": {"enabled": ["register_filesystem"]},
        }
    )
    if fail:
        with pytest.raises(ExecutionError) as captured:
            run([first, second], config=config)
        assert captured.value.sql_file == second
        assert captured.value.statement_number == 2
        assert "deliberate" not in str(captured.value)
    else:
        run([first, second], config=config)
    assert azure_data and all(client.closed for client in azure_data)
    with duckdb.connect(str(database)) as connection:
        assert connection.list_filesystems() == []
        assert connection.execute("SELECT * FROM result").fetchall() == [(42,)]


@pytest.mark.parametrize("kind", ["connection_string", "managed_identity"])
def test_existing_prefect_blocks_construct_filesystem_strategies(kind: str) -> None:
    pytest.importorskip("prefect")
    from quackframe.credential_loading.providers.prefect.blocks import (
        AzureConnectionStringCredentials,
        AzureManagedIdentityCredentials,
    )

    if kind == "connection_string":
        block = AzureConnectionStringCredentials(
            connection_string=SecretStr(CONNECTION)
        )
        model = block.to_credentials(AzureConnectionStringFilesystem)
    else:
        block = AzureManagedIdentityCredentials(account_name="examplestorage")
        model = block.to_credentials(AzureManagedIdentityFilesystem)
    resolved = model.resolve_overrides({"scope": "az://reports/"})
    assert type(resolved) is type(model)
    assert model.scope is None
    assert resolved.scope == "az://reports/"
    with pytest.raises(ValueError, match="override"):
        model.resolve_overrides({"client_id": "other"})


@pytest.mark.parametrize(
    "path", ["reports-files://reports", "reports-files://reports/"]
)
def test_container_root_paths(path: str) -> None:
    to_backend, _, _ = azure.azure_paths("reports-files")
    assert to_backend(path).rstrip("/") == "reports"
