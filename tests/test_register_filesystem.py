"""Filesystem SQL, shared loading and standard backend registration behaviour."""

from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from stat import S_IFREG
from types import SimpleNamespace
from typing import ClassVar, Self, TypeVar
from unittest.mock import Mock, patch

import duckdb
import pytest
from duckdb import DuckDBPyConnection
from pydantic import SecretStr

from quackframe import QuackframeConfig, run
from quackframe.credential_loading import loading
from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.providers import registry
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem import models
from quackframe.sql_functions.register_filesystem.function import register_filesystem
from quackframe.sql_functions.register_filesystem.models import (
    DuckDBFilesystem,
    SftpFilesystem,
)
from quackframe.sql_functions.register_secret.models import SshPrivateKeySecret

T = TypeVar("T", bound=CredentialModel)


def sftp_credentials(
    scope: str = "sftp://files.example.test/reports/",
) -> SftpFilesystem:
    return SftpFilesystem(
        username=SecretStr("protected-reader"),
        key_path="/run/secrets/protected-key",
        port=2222,
        scope=scope,
    )


@pytest.mark.parametrize(
    ("arguments", "expected_scope"),
    [
        ("'example', 'source_files', 'sftp'", "sftp://files.example.test/reports/"),
        (
            "'example', 'source_files', 'sftp', NULL",
            "sftp://files.example.test/reports/",
        ),
        (
            "'example', 'source_files', 'sftp', MAP {}",
            "sftp://files.example.test/reports/",
        ),
        (
            "provider := 'example', reference := 'source_files', "
            "filesystem_type := 'sftp', "
            "overrides := MAP {'scope': 'sftp://other.example.test/'}",
            "sftp://other.example.test/",
        ),
    ],
)
def test_filesystem_sql_resolves_overrides_without_mutating_credentials(
    monkeypatch: pytest.MonkeyPatch, arguments: str, expected_scope: str
) -> None:
    original = sftp_credentials()
    provider = Mock()
    provider.resolve.return_value = original
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    registered: list[SftpFilesystem] = []

    def register(model: SftpFilesystem, connection: DuckDBPyConnection) -> None:
        assert connection.execute("SELECT 1").fetchone() == (1,)
        registered.append(model)

    monkeypatch.setattr(SftpFilesystem, "register_filesystem_protocol", register)
    with duckdb.connect() as connection:
        install_functions(connection, ("register_filesystem",))
        result = connection.execute(
            f"SELECT quackframe.register_filesystem({arguments})"
        ).fetchone()

    assert result == (True,)
    provider.resolve.assert_called_once_with("source_files", SftpFilesystem)
    assert len(registered) == 1
    assert type(registered[0]) is SftpFilesystem
    assert registered[0].scope == expected_scope
    assert registered[0].key_path == original.key_path
    assert original.scope == "sftp://files.example.test/reports/"


@pytest.mark.parametrize(
    "overrides",
    [
        {"scope": ""},
        {"scope": " "},
        {"scope": "https://files.example.test/"},
        {"scope": "sftp://protected-reader:password@files.example.test/"},
        {"scope": "sftp://files.example.test:22/"},
        {"scope": "sftp://files.example.test:invalid/"},
        {"scope": "sftp://files.example.test/?token=protected-value"},
        {"scope": "sftp://files.example.test/#protected-value"},
        {"scope": "sftp:///reports/"},
        {"username": "protected-value"},
        {"key_path": "protected-value"},
        {"port": "protected-value"},
        {"host_key_fingerprint": "protected-value"},
        {"unknown": "protected-value"},
    ],
)
def test_invalid_overrides_fail_safely_before_backend_construction(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    pytest.importorskip("fsspec.implementations.sftp")
    provider = Mock()
    provider.resolve.return_value = sftp_credentials()
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))

    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
        ) as constructor,
        duckdb.connect() as connection,
        pytest.raises(ValueError) as captured,
    ):
        register_filesystem(connection, "example", "source_files", "sftp", overrides)

    constructor.assert_not_called()
    assert "protected" not in str(captured.value)
    assert "password@" not in str(captured.value)


@pytest.mark.parametrize(
    "scope", ["sftp://files.example.test:2222/reports/", "ssh://files.example.test/"]
)
def test_sftp_uses_standard_constructor_and_registers_the_same_object(
    scope: str,
) -> None:
    pytest.importorskip("fsspec.implementations.sftp")
    connection = Mock(spec=DuckDBPyConnection)
    with patch(
        "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
    ) as constructor:
        sftp_credentials(scope).register_filesystem_protocol(connection)

    constructor.assert_called_once_with(
        host="files.example.test",
        username="protected-reader",
        key_filename="/run/secrets/protected-key",
        port=2222,
        host_key_fingerprint=None,
        skip_instance_cache=True,
    )
    connection.register_filesystem.assert_called_once_with(constructor.return_value)
    constructor.return_value.client.close.assert_not_called()
    constructor.return_value.ftp.close.assert_not_called()


def test_failed_registration_closes_unowned_clients_and_hides_backend_errors() -> None:
    pytest.importorskip("fsspec.implementations.sftp")
    connection = Mock(spec=DuckDBPyConnection)
    connection.register_filesystem.side_effect = RuntimeError("protected-value")
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
        ) as constructor,
        pytest.raises(RuntimeError, match="could not be registered") as captured,
    ):
        constructor.return_value.ftp.close.side_effect = RuntimeError("close-failure")
        sftp_credentials().register_filesystem_protocol(connection)

    constructor.return_value.ftp.close.assert_called_once()
    constructor.return_value.client.close.assert_called_once()
    assert "protected-value" not in str(captured.value)
    assert "close-failure" not in str(captured.value)


def test_failed_sftp_connection_has_safe_diagnostics() -> None:
    pytest.importorskip("fsspec.implementations.sftp")
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem",
            side_effect=RuntimeError("protected-key"),
        ),
        pytest.raises(RuntimeError, match="could not connect") as captured,
    ):
        sftp_credentials().register_filesystem_protocol(Mock(spec=DuckDBPyConnection))

    assert "protected-key" not in str(captured.value)


def test_serialized_sftp_backend_registers_both_protocols() -> None:
    pytest.importorskip("fsspec.implementations.sftp")
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SSHClient"
        ) as client_type,
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient.from_transport"
        ) as channel,
        duckdb.connect() as connection,
    ):
        content = b"value\n42\n"
        ftp = channel.return_value
        ftp.stat.return_value = SimpleNamespace(
            st_mode=S_IFREG,
            st_size=len(content),
            st_uid=0,
            st_gid=0,
            st_atime=0,
            st_mtime=0,
        )

        def open_file(*args: object, **kwargs: object) -> BytesIO:
            return BytesIO(content)

        ftp.open.side_effect = open_file
        sftp_credentials().register_filesystem_protocol(connection)

        assert connection.list_filesystems() == ["sftp"]
        for scheme in ("sftp", "ssh"):
            assert connection.execute(
                "SELECT value FROM read_csv(?)",
                [f"{scheme}://files.example.test/report.csv"],
            ).fetchone() == (42,)
        client_type.return_value.connect.assert_called_once_with(
            "files.example.test",
            username="protected-reader",
            key_filename="/run/secrets/protected-key",
            port=2222,
        )
        channel.assert_called_once_with(
            client_type.return_value.get_transport.return_value
        )
        client_type.return_value.open_sftp.assert_not_called()


def test_unknown_filesystem_fails_before_provider_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_provider = Mock()
    monkeypatch.setattr(loading, "get_provider", get_provider)
    with pytest.raises(ValueError, match="Unsupported filesystem type"):
        register_filesystem(Mock(), "example", "source_files", "unknown")
    get_provider.assert_not_called()


class MemoryFilesystem(DuckDBFilesystem):
    """Exercise a second strategy through the unchanged SQL and provider paths."""

    credential_type: ClassVar[str] = "test_memory"
    filesystem_type: ClassVar[str] = "test_memory"

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        self.validate_override_keys(overrides)
        return self.model_copy()

    def register_filesystem_protocol(self, connection: DuckDBPyConnection) -> None:
        from fsspec.implementations.memory import (  # pyright: ignore[reportMissingTypeStubs]
            MemoryFileSystem,
        )

        filesystem = MemoryFileSystem(skip_instance_cache=True)
        filesystem.pipe_file(  # pyright: ignore[reportUnknownMemberType]
            "/quackframe-test/report.csv", b"value\n42\n"
        )
        connection.register_filesystem(filesystem)


class ExampleProvider:
    def resolve(self, reference: str, model_type: type[T]) -> T:
        assert reference == "example_reference"
        return model_type()


def install_example_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    registration = registry.ProviderRegistration(
        name="example",
        module_name=__name__,
        implementation_name="ExampleProvider",
        missing_dependency="example",
        missing_dependency_message="Install example support",
    )
    monkeypatch.setattr(registry, "PROVIDER_REGISTRY", (registration,))
    monkeypatch.setitem(models.FILESYSTEM_MODELS, "test_memory", MemoryFilesystem)


def test_added_provider_and_strategy_work_across_ordered_sql_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fsspec")
    install_example_provider(monkeypatch)
    first = tmp_path / "register.sql"
    first.write_text(
        "SELECT quackframe.register_filesystem('example', "
        "'example_reference', 'test_memory');",
        encoding="utf-8",
    )
    second = tmp_path / "read.sql"
    second.write_text(
        "CREATE TABLE result AS SELECT * FROM "
        "read_csv('memory:///quackframe-test/*.csv');",
        encoding="utf-8",
    )
    database = tmp_path / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": tmp_path,
            "functions": {"enabled": ["register_filesystem"]},
            "database": {"mode": "persistent", "path": database},
        }
    )

    run([first, second], config=config)

    with duckdb.connect(str(database)) as connection:
        assert connection.execute("SELECT value FROM result").fetchall() == [(42,)]
        assert not connection.filesystem_is_registered("memory")


def test_repeated_registration_preserves_duckdb_backend_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fsspec")
    install_example_provider(monkeypatch)
    with duckdb.connect() as connection:
        register_filesystem(connection, "example", "example_reference", "test_memory")
        # DuckDB owns collision handling; Quackframe adds no endpoint registry.
        with pytest.raises(duckdb.Error, match="already been registered"):
            register_filesystem(
                connection, "example", "example_reference", "test_memory"
            )
        assert connection.execute(
            "SELECT value FROM read_csv('memory:///quackframe-test/report.csv')"
        ).fetchone() == (42,)


def test_ssh_strategies_preserve_concrete_type_and_share_override_behavior() -> None:
    original = sftp_credentials()
    for model in [original, SshPrivateKeySecret(**original.model_dump())]:
        resolved = model.resolve_overrides({"scope": "sftp://other.example.test/"})
        assert type(resolved) is type(model)
        assert resolved is not model
        assert model.scope == "sftp://files.example.test/reports/"
        assert resolved.scope == "sftp://other.example.test/"
        assert resolved.username == model.username
