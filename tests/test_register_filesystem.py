"""Protocol routing, resource ownership and credential resolution regressions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self, TypeVar
from unittest.mock import Mock, patch
from uuid import uuid4

import duckdb
import pytest
from pydantic import SecretStr

from quackframe import ExecutionError, QuackframeConfig, run
from quackframe.credential_loading import loading
from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.providers import registry
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem import models
from quackframe.sql_functions.register_filesystem.function import register_filesystem
from quackframe.sql_functions.register_filesystem.models import (
    DuckDBFilesystem,
    SftpFilesystem,
)
from quackframe.sql_functions.register_secret.models import SshPrivateKeySecret

if TYPE_CHECKING:
    from quackframe.sql_functions.register_filesystem.adapter import ProtocolFileSystem

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


class MemoryFilesystem(DuckDBFilesystem):
    extra_dependency_bundle: ClassVar[str] = "test_memory"
    credential_type: ClassVar[str] = "test_memory"
    filesystem_type: ClassVar[str] = "test_memory"
    value: int = 42
    allowed_overrides: ClassVar[frozenset[str]] = frozenset({"value"})
    closed: ClassVar[list[str]] = []

    def resolve_overrides(self, overrides: Mapping[str, str]) -> Self:
        self.validate_override_keys(overrides)
        return self.model_copy(
            update={"value": int(overrides.get("value", self.value))}
        )

    def create_filesystem(self, protocol: str) -> ProtocolFileSystem:
        from fsspec.implementations.memory import (  # pyright: ignore[reportMissingTypeStubs]
            MemoryFileSystem,
        )

        from quackframe.sql_functions.register_filesystem.adapter import (
            ProtocolFileSystem,
        )

        backend = MemoryFileSystem(skip_instance_cache=True)
        root = "/" + uuid4().hex
        backend.pipe_file(  # pyright: ignore[reportUnknownMemberType]
            root + "/report.csv", f"value\n{self.value}\n".encode()
        )

        def to_backend(path: str) -> str:
            prefix = protocol + ":///"
            if not path.startswith(prefix):
                raise ValueError("Invalid memory URL")
            return root + "/" + path[len(prefix) :]

        def close() -> None:
            self.closed.append(protocol)
            backend.rm(root, recursive=True)  # pyright: ignore[reportUnknownMemberType]

        return ProtocolFileSystem(
            backend,
            protocol,
            to_backend,
            lambda path: protocol + "://" + path.removeprefix(root),
            close,
            skip_instance_cache=True,
        )


class ExampleProvider:
    calls: ClassVar[int] = 0

    def resolve(self, reference: str, model_type: type[T]) -> T:
        type(self).calls += 1
        return model_type()


@pytest.fixture
def sftp_dependencies() -> None:
    pytest.importorskip("fsspec")
    pytest.importorskip("paramiko")


@pytest.fixture
def memory_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fsspec")
    ExampleProvider.calls = 0
    MemoryFilesystem.closed.clear()
    monkeypatch.setattr(
        registry,
        "PROVIDER_REGISTRY",
        (
            registry.ProviderRegistration(
                name="example",
                module_name=__name__,
                implementation_name="ExampleProvider",
                missing_dependency="example",
                missing_dependency_message="Install example support",
            ),
        ),
    )
    monkeypatch.setitem(models.FILESYSTEM_MODELS, "test_memory", MemoryFilesystem)


@pytest.mark.parametrize(
    "arguments",
    [
        "'example', 'source-files', 'test_memory'",
        "'example', 'ignored', 'test_memory', 'source-files'",
        "'example', 'source-files', 'test_memory', NULL, NULL",
        "'example', 'source-files', 'test_memory', NULL, MAP {}",
        "provider := 'example', reference := 'ignored', "
        "filesystem_type := 'test_memory', "
        "protocol := 'source-files'",
        "'example', 'source-files', 'test_memory', overrides := MAP {}",
    ],
)
def test_sql_forms_read_and_discover_the_selected_protocol(
    memory_provider: None, arguments: str
) -> None:
    with duckdb.connect() as connection:
        with SessionResources(connection) as resources:
            install_functions(connection, ("register_filesystem",), resources)
            assert connection.execute(
                f"SELECT quackframe.register_filesystem({arguments})"
            ).fetchone() == (True,)
            paths = connection.execute(
                "SELECT file FROM glob('source-files:///*.csv')"
            ).fetchall()
            assert paths == [("source-files:///report.csv",)]
            assert connection.execute(
                "SELECT value, filename FROM read_csv(?, filename=true)",
                [[p[0] for p in paths]],
            ).fetchall() == [(42, "source-files:///report.csv")]
            assert connection.execute(
                "SELECT filename, content FROM read_blob(?)", [[p[0] for p in paths]]
            ).fetchall() == [("source-files:///report.csv", b"value\n42\n")]
        assert connection.list_filesystems() == []
    assert MemoryFilesystem.closed == ["source-files"]
    assert ExampleProvider.calls == 1


def test_independent_instances_and_collision_preserve_existing_reads(
    memory_provider: None,
) -> None:
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        register_filesystem(resources, "example", "first", "test_memory")
        register_filesystem(
            resources,
            "example",
            "first",
            "test_memory",
            "second",
            {"value": "99"},
        )
        with pytest.raises(ValueError, match="already registered"):
            register_filesystem(resources, "example", "first", "test_memory")
        with connection.duplicate() as duplicate:
            assert duplicate.execute(
                "SELECT * FROM read_csv(['first:///report.csv', "
                "'second:///report.csv']) "
                "ORDER BY value"
            ).fetchall() == [(42,), (99,)]
    assert sorted(MemoryFilesystem.closed) == ["first", "second"]


@pytest.mark.parametrize(
    "protocol",
    [
        "",
        "UPPER",
        "has_under",
        "1bad",
        "sftp",
        "ssh",
        "s3",
        "https",
        "file",
        "az",
        "memory",
    ],
)
def test_invalid_and_reserved_protocols_fail_before_loading(
    monkeypatch: pytest.MonkeyPatch, protocol: str
) -> None:
    if protocol in {"sftp", "ssh", "s3", "https", "file", "az", "memory"}:
        pytest.importorskip("fsspec")
    provider = Mock()
    monkeypatch.setattr(loading, "get_provider", provider)
    with (
        duckdb.connect() as connection,
        SessionResources(connection) as resources,
        pytest.raises(ValueError),
    ):
        register_filesystem(resources, "example", "reference", "sftp", protocol)
    provider.assert_not_called()


def test_unknown_type_fails_before_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = Mock()
    monkeypatch.setattr(loading, "get_provider", provider)
    with (
        SessionResources(Mock()) as resources,
        pytest.raises(ValueError, match="Unsupported filesystem type"),
    ):
        register_filesystem(resources, "example", "reference", "unknown")
    provider.assert_not_called()


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
@pytest.mark.usefixtures("sftp_dependencies")
def test_invalid_overrides_fail_safely_before_backend_construction(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    provider = Mock()
    provider.resolve.return_value = sftp_credentials()
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))

    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
        ) as constructor,
        duckdb.connect() as connection,
        SessionResources(connection) as resources,
        pytest.raises(ValueError) as captured,
    ):
        register_filesystem(
            resources,
            "example",
            "source-files",
            "sftp",
            overrides=overrides,
        )

    constructor.assert_not_called()
    assert "protected" not in str(captured.value)
    assert "password@" not in str(captured.value)


@pytest.mark.parametrize(
    "scope", ["sftp://files.example.test:2222/reports/", "ssh://files.example.test/"]
)
@pytest.mark.usefixtures("sftp_dependencies")
def test_sftp_constructor_and_endpoint_mapping(scope: str) -> None:
    with patch(
        "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
    ) as constructor:
        filesystem = sftp_credentials(scope).create_filesystem("supplier")
    constructor.assert_called_once_with(
        host="files.example.test",
        username="protected-reader",
        key_filename="/run/secrets/protected-key",
        port=2222,
        host_key_fingerprint=None,
        skip_instance_cache=True,
    )
    assert (
        filesystem.to_backend("supplier://files.example.test/reports/a.csv")
        == "/reports/a.csv"
    )
    assert (
        filesystem.from_backend("/reports/a.csv")
        == "supplier://files.example.test:2222/reports/a.csv"
    )
    for path in [
        "supplier://other.test/a",
        "supplier://files.example.test:22/a",
        "supplier://user@files.example.test/a",
        "supplier://files.example.test/a?secret=x",
        "supplier://files.example.test/a?",
        "other://files.example.test/a",
    ]:
        with pytest.raises(ValueError, match="registered endpoint"):
            filesystem.to_backend(path)
    constructor.return_value.ftp.close.side_effect = RuntimeError("close failure")
    with pytest.raises(RuntimeError):
        filesystem.close_backend()
    constructor.return_value.client.close.assert_called_once()


@pytest.mark.usefixtures("sftp_dependencies")
@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("daily-?.csv", "/reports/daily-?.csv"),
        ("daily-?", "/reports/daily-?"),
        ("daily-%3F?.csv", "/reports/daily-[?]?.csv"),
        ("daily-%253F?.csv", "/reports/daily-%3F?.csv"),
    ],
)
def test_sftp_question_mark_globs_preserve_raw_and_encoded_characters(
    pattern: str, expected: str
) -> None:
    with patch(
        "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
    ):
        filesystem = sftp_credentials().create_filesystem("supplier")
    path = "supplier://files.example.test/reports/" + pattern
    assert filesystem.to_glob(path) == expected


@pytest.mark.usefixtures("sftp_dependencies")
@pytest.mark.parametrize(
    "path",
    [
        "supplier://other.test/daily-?.csv",
        "supplier://files.example.test:22/daily-?.csv",
        "supplier://user@files.example.test/daily-?.csv",
        "supplier://files.example.test/daily-?.csv#fragment",
        "supplier://files.example.test?other.test/daily-?.csv",
        "supplier://files.example.test?",
        "other://files.example.test/daily-?.csv",
    ],
)
def test_sftp_question_mark_globs_reject_invalid_endpoints(path: str) -> None:
    with patch(
        "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
    ) as constructor:
        filesystem = sftp_credentials().create_filesystem("supplier")
    with pytest.raises(ValueError, match="registered endpoint"):
        filesystem.glob(path)
    constructor.return_value.glob.assert_not_called()


@pytest.mark.usefixtures("sftp_dependencies")
def test_failed_sftp_connection_has_safe_diagnostics() -> None:
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem",
            side_effect=RuntimeError("protected-key"),
        ),
        pytest.raises(RuntimeError, match="could not connect") as captured,
    ):
        sftp_credentials().create_filesystem("supplier")
    assert "protected-key" not in str(captured.value)


@pytest.mark.parametrize("fail", [False, True])
def test_ordered_files_cleanup_on_success_and_failure(
    memory_provider: None, tmp_path: Path, fail: bool
) -> None:
    first = tmp_path / "register.sql"
    first.write_text(
        "SELECT quackframe.register_filesystem('example', 'source-files', "
        "'test_memory');"
    )
    second = tmp_path / "read.sql"
    second.write_text(
        "CREATE TABLE result AS SELECT * FROM read_csv('source-files:///*.csv');"
        + ("SELECT error('deliberate');" if fail else "")
    )
    database = tmp_path / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": tmp_path,
            "functions": {"enabled": ["register_filesystem"]},
            "database": {"mode": "persistent", "path": database},
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
    assert MemoryFilesystem.closed == ["source-files"]
    with duckdb.connect(str(database)) as connection:
        assert connection.list_filesystems() == []
        assert connection.execute("SELECT * FROM result").fetchall() == [(42,)]


def test_ssh_strategies_preserve_concrete_type_and_share_override_behavior() -> None:
    original = sftp_credentials()
    for model in [original, SshPrivateKeySecret(**original.model_dump())]:
        resolved = model.resolve_overrides({"scope": "sftp://other.example.test/"})
        assert type(resolved) is type(model)
        assert resolved is not model
        assert model.scope == "sftp://files.example.test/reports/"
        assert resolved.username == model.username


def test_failed_duckdb_registration_closes_new_backend(memory_provider: None) -> None:
    connection = Mock()
    duplicate = connection.duplicate.return_value
    duplicate.filesystem_is_registered.return_value = False
    duplicate.list_filesystems.return_value = []
    duplicate.register_filesystem.side_effect = RuntimeError("protected-value")
    with (
        SessionResources(connection) as resources,
        pytest.raises(RuntimeError, match="could not be registered") as captured,
    ):
        register_filesystem(resources, "example", "source-files", "test_memory")
    assert MemoryFilesystem.closed == ["source-files"]
    duplicate.close.assert_called_once()
    assert "protected-value" not in str(captured.value)


def test_external_registration_collision_is_preserved(memory_provider: None) -> None:
    external = MemoryFilesystem(value=7).create_filesystem("external")
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        connection.register_filesystem(external)
        try:
            with pytest.raises(ValueError, match="already registered"):
                register_filesystem(resources, "example", "external", "test_memory")
            assert connection.execute(
                "SELECT * FROM read_csv('external:///report.csv')"
            ).fetchone() == (7,)
            assert ExampleProvider.calls == 0
        finally:
            connection.unregister_filesystem("external")
            external.close_backend()


def test_concurrent_duplicate_protocol_connects_only_once(
    memory_provider: None,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with duckdb.connect() as connection, SessionResources(connection) as resources:

        def register(_: int) -> bool:
            with connection.duplicate():
                try:
                    return register_filesystem(
                        resources, "example", "concurrent", "test_memory"
                    )
                except ValueError:
                    return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(register, range(2))) == [False, True]
        assert ExampleProvider.calls == 1
        assert connection.execute(
            "SELECT * FROM read_csv('concurrent:///report.csv')"
        ).fetchone() == (42,)


def test_resource_bound_install_requires_owner_before_catalog_changes() -> None:
    with duckdb.connect() as connection:
        with pytest.raises(RuntimeError, match="SessionResources"):
            install_functions(connection, ("register_filesystem",))
        assert connection.execute(
            "SELECT count(*) FROM information_schema.schemata "
            "WHERE schema_name='quackframe'"
        ).fetchone() == (0,)


@pytest.mark.usefixtures("sftp_dependencies")
def test_sftp_credentials_are_isolated_on_same_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from io import BytesIO

    def resolve(reference: str, model_type: type[SftpFilesystem]) -> SftpFilesystem:
        return model_type(
            username=SecretStr(reference), key_path="/key", scope="sftp://files.test"
        )

    provider = Mock()
    provider.resolve.side_effect = resolve
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    clients: list[Mock] = []

    def backend(**kwargs: object) -> Mock:
        content = b"value\n1\n" if kwargs["username"] == "first" else b"value\n2\n"
        client = Mock()

        def open_file(*args: object, **kwargs: object) -> BytesIO:
            return BytesIO(content)

        client.open.side_effect = open_file
        client.glob.return_value = ["/report.csv"]
        client.info.return_value = {
            "name": "/report.csv",
            "size": len(content),
            "type": "file",
        }
        clients.append(client)
        return client

    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem",
            side_effect=backend,
        ),
        duckdb.connect() as connection,
        SessionResources(connection) as resources,
    ):
        register_filesystem(resources, "example", "first", "sftp")
        register_filesystem(resources, "example", "second", "sftp")
        assert connection.execute(
            "SELECT * FROM read_csv(['first://files.test/report.csv', "
            "'second://files.test/report.csv']) ORDER BY value"
        ).fetchall() == [(1,), (2,)]
    for client in clients:
        client.ftp.close.assert_called_once()
        client.client.close.assert_called_once()


@pytest.mark.usefixtures("sftp_dependencies")
def test_sql_scope_override_loads_once_without_mutating_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = sftp_credentials()
    provider = Mock()
    provider.resolve.return_value = original
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem"
        ) as constructor,
        duckdb.connect() as connection,
        SessionResources(connection) as resources,
    ):
        install_functions(connection, ("register_filesystem",), resources)
        assert connection.execute(
            "SELECT quackframe.register_filesystem('example', 'source-files', "
            "'sftp', overrides := MAP {'scope': 'sftp://other.test/'})"
        ).fetchone() == (True,)
        constructor.assert_called_once_with(
            host="other.test",
            username="protected-reader",
            key_filename="/run/secrets/protected-key",
            port=2222,
            host_key_fingerprint=None,
            skip_instance_cache=True,
        )
    provider.resolve.assert_called_once_with("source-files", SftpFilesystem)
    assert original.scope == "sftp://files.example.test/reports/"
    constructor.return_value.ftp.close.assert_called_once()
    constructor.return_value.client.close.assert_called_once()


def test_external_secondary_protocol_cannot_capture_new_reads(
    memory_provider: None,
) -> None:
    external = MemoryFilesystem(value=7).create_filesystem("external")
    external.protocol = ("external", "hidden")  # pyright: ignore[reportAttributeAccessIssue]
    with duckdb.connect() as connection, SessionResources(connection) as resources:
        connection.register_filesystem(external)
        try:
            assert not connection.filesystem_is_registered("hidden")
            with pytest.raises(ValueError, match="cannot be verified"):
                register_filesystem(resources, "example", "hidden", "test_memory")
            assert ExampleProvider.calls == 0
        finally:
            connection.unregister_filesystem("external")
            external.close_backend()


@pytest.mark.usefixtures("sftp_dependencies")
@pytest.mark.parametrize(
    "filename",
    [
        "report#1.csv",
        "report%2F1.csv",
        "report?1.csv",
        "report*1.csv",
        "report[1].csv",
        "report space.csv",
        "rapport-é.csv",
    ],
)
def test_discovered_sftp_filenames_round_trip_through_duckdb(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    from urllib.parse import quote

    from fsspec.implementations.memory import (  # pyright: ignore[reportMissingTypeStubs]
        MemoryFileSystem,
    )

    backend = MemoryFileSystem(skip_instance_cache=True)
    root = "/" + uuid4().hex
    content = b"value\n42\n"
    backend.pipe_file(root + "/" + filename, content)  # pyright: ignore[reportUnknownMemberType]

    # These would also match if decoded ?/*/brackets became glob operators.
    for decoy in ["reportX1.csv", "report1.csv"]:
        backend.pipe_file(root + "/" + decoy, b"value\n99\n")  # pyright: ignore[reportUnknownMemberType]

    client = Mock(
        open=backend.open,  # pyright: ignore[reportUnknownMemberType]
        glob=backend.glob,  # pyright: ignore[reportUnknownMemberType]
        info=backend.info,  # pyright: ignore[reportUnknownMemberType]
    )

    provider = Mock()
    provider.resolve.return_value = sftp_credentials()
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))

    expected = (
        "source://files.example.test:2222" + root + "/" + quote(filename, safe="")
    )

    try:
        with (
            patch(
                "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem",
                return_value=client,
            ),
            duckdb.connect() as connection,
            SessionResources(connection) as resources,
        ):
            register_filesystem(resources, "example", "source", "sftp")

            discovered = connection.execute(
                "SELECT file FROM glob(?)",
                ["source://files.example.test" + root + "/*.csv"],
            ).fetchall()
            assert (expected,) in discovered
            assert connection.execute(
                "SELECT filename, content FROM read_blob(?)", [[expected]]
            ).fetchall() == [(expected, content)]
            assert connection.execute(
                "SELECT value, filename FROM read_csv(?, filename=true)", [[expected]]
            ).fetchall() == [(42, expected)]
    finally:
        backend.rm(root, recursive=True)  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.usefixtures("sftp_dependencies")
@pytest.mark.parametrize(
    ("pattern", "filename"),
    [
        ("daily-?.csv", "daily-1.csv"),
        ("daily-?", "daily-1"),
        ("daily-%3F?.csv", "daily-?1.csv"),
    ],
)
def test_sftp_question_mark_globs_select_files_through_duckdb(
    pattern: str, filename: str
) -> None:
    from urllib.parse import quote

    from fsspec.implementations.memory import (  # pyright: ignore[reportMissingTypeStubs]
        MemoryFileSystem,
    )

    backend = MemoryFileSystem(skip_instance_cache=True)
    root = "/" + uuid4().hex
    for name in [filename, "daily-", "daily-12.csv", "daily-X1.csv"]:
        backend.pipe_file(root + "/" + name, b"value\n42\n")  # pyright: ignore[reportUnknownMemberType]
    client = Mock(glob=backend.glob)  # pyright: ignore[reportUnknownMemberType]
    expected = (
        "source://files.example.test:2222" + root + "/" + quote(filename, safe="")
    )

    try:
        with (
            patch(
                "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPFileSystem",
                return_value=client,
            ),
            duckdb.connect() as connection,
        ):
            filesystem = sftp_credentials().create_filesystem("source")
            connection.register_filesystem(filesystem)
            try:
                assert connection.execute(
                    "SELECT file FROM glob(?)",
                    ["source://files.example.test" + root + "/" + pattern],
                ).fetchall() == [(expected,)]
            finally:
                connection.unregister_filesystem("source")
                filesystem.close_backend()
    finally:
        backend.rm(root, recursive=True)  # pyright: ignore[reportUnknownMemberType]
