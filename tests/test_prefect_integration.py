"""Optional Prefect runtime and Block provider tests."""

from pathlib import Path
from typing import ClassVar
from unittest.mock import ANY, Mock, patch

import duckdb
import pytest
from pydantic import SecretStr

prefect = pytest.importorskip("prefect")

from prefect.testing.utilities import prefect_test_harness  # noqa: E402

from quackframe import QuackframeConfig, load_config, run  # noqa: E402
from quackframe.credential_loading import loading  # noqa: E402
from quackframe.credential_loading.providers.prefect.blocks import (  # noqa: E402
    AzureConnectionStringCredentials,
    AzureManagedIdentityCredentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)
from quackframe.credential_loading.providers.prefect.provider import (  # noqa: E402
    PrefectCredentialProvider,
)
from quackframe.integrations.prefect import runtime as prefect_runtime  # noqa: E402
from quackframe.sql import PreparedSqlFile, prepare_sql_files  # noqa: E402
from quackframe.sql_functions.installer import install_functions  # noqa: E402
from quackframe.sql_functions.register_filesystem.models import (  # noqa: E402
    SftpFilesystem,
)
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    AzureConnectionStringSecret,
    AzureManagedIdentitySecret,
    MssqlSecret,
    SshPrivateKeySecret,
)


def test_prefect_runtime_preserves_order_and_shared_session(tmp_path: Path) -> None:
    first = tmp_path / "01-create.sql"
    first.write_text("CREATE TEMP TABLE state(value INTEGER);", encoding="utf-8")
    second = tmp_path / "02-use.sql"
    second.write_text("INSERT INTO state VALUES (1);", encoding="utf-8")

    with prefect_test_harness():
        result = run(
            [first, second],
            config=QuackframeConfig(root=tmp_path, runtime="prefect"),
        )

    assert result.runtime == "prefect"
    assert tuple(file.path.name for file in result.files) == (
        "01-create.sql",
        "02-use.sql",
    )


def test_dotenv_permission_allows_prefect_result_logging(tmp_path: Path) -> None:
    sql_file = tmp_path / "result.sql"
    sql_file.write_text(
        "-- quackframe: log-result\nSELECT 'visible' AS value;",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        'QUACKFRAME_RUNTIME="prefect"\n'
        'QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING="true"\n',
        encoding="utf-8",
    )
    config = load_config(root=tmp_path, environ={})

    with prefect_test_harness():
        result = run([sql_file], config=config)

    assert result.runtime == "prefect"


def test_prefect_flow_has_a_stable_name() -> None:
    assert prefect_runtime.execute_plan_flow.name == "quackframe-run"


def test_prefect_file_task_uses_the_path_stem(tmp_path: Path) -> None:
    task_call = Mock()
    sql_file = PreparedSqlFile(
        path=tmp_path / "01-load-data.sql",
        statements=(),
    )

    with patch.object(
        prefect_runtime.execute_sql_file_task,
        "with_options",
        return_value=task_call,
    ) as with_options:
        prefect_runtime._execute_named_file_task(  # pyright: ignore[reportPrivateUsage]
            Mock(),
            sql_file,
        )

    with_options.assert_called_once_with(name="01-load-data")
    task_call.assert_called_once_with(ANY, sql_file)


def test_prefect_flow_run_uses_project_name(tmp_path: Path) -> None:
    configured_flow = Mock()
    configured_flow.return_value = Mock()
    config = QuackframeConfig(
        root=tmp_path,
        runtime="prefect",
        project_name="analytics-workflows",
    )

    with patch.object(
        prefect_runtime.execute_plan_flow,
        "with_options",
        return_value=configured_flow,
    ) as with_options:
        prefect_runtime.execute_with_prefect((), config)

    with_options.assert_called_once_with(flow_run_name="analytics-workflows")


def test_prefect_file_task_logs_selected_result(
    tmp_path: Path,
) -> None:
    sql_file_path = tmp_path / "result.sql"
    sql_file_path.write_text(
        "-- quackframe: log-result\nSELECT 'visible' AS value;",
        encoding="utf-8",
    )
    config = QuackframeConfig(
        root=tmp_path,
        runtime="prefect",
        allow_external_result_logging=True,
    )
    sql_file = prepare_sql_files(
        [sql_file_path],
        root=tmp_path,
        log_setting=config.log_setting,
    )[0]
    logger = Mock()

    with (
        duckdb.connect() as connection,
        patch.object(prefect_runtime, "get_run_logger", return_value=logger),
    ):
        prefect_runtime.execute_sql_file_task.fn(connection, sql_file)

    rendered_result = logger.info.call_args.args[0]
    assert "visible" in rendered_result
    logger.info.assert_called_once()


def test_prefect_warns_once_before_external_results(tmp_path: Path) -> None:
    sql_file_path = tmp_path / "result.sql"
    sql_file_path.write_text("SELECT 'visible';", encoding="utf-8")
    config = QuackframeConfig(
        root=tmp_path,
        runtime="prefect",
        log_setting="all",
        allow_external_result_logging=True,
    )
    sql_files = prepare_sql_files(
        [sql_file_path],
        root=tmp_path,
        log_setting=config.log_setting,
    )
    logger = Mock()

    with (
        patch.object(prefect_runtime, "get_run_logger", return_value=logger),
        patch.object(prefect_runtime, "execute_plan", return_value=Mock()),
    ):
        prefect_runtime.execute_plan_flow.fn(sql_files, config)

    logger.warning.assert_called_once()


def test_prefect_provider_rejects_unknown_credential_type() -> None:
    class UnsupportedCredentials(MssqlSecret):
        credential_type: ClassVar[str] = "future_type"

    with pytest.raises(ValueError, match="Unsupported Prefect credential type"):
        PrefectCredentialProvider().resolve(
            "shared-secret",
            UnsupportedCredentials,
        )


def test_prefect_provider_translates_mssql_block() -> None:
    block = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with patch.object(MssqlCredentials, "load", return_value=block) as load:
        credentials = PrefectCredentialProvider().resolve("shared_login", MssqlSecret)

    load.assert_called_once_with("shared-login")
    assert isinstance(credentials, MssqlSecret)
    assert credentials.database is None
    assert credentials.password.get_secret_value() == "sensitive"


def test_prefect_provider_translates_azure_block() -> None:
    block = AzureConnectionStringCredentials(connection_string=SecretStr("sensitive"))

    with patch.object(
        AzureConnectionStringCredentials,
        "load",
        return_value=block,
    ) as load:
        credentials = PrefectCredentialProvider().resolve(
            "shared_storage",
            AzureConnectionStringSecret,
        )

    load.assert_called_once_with("shared-storage")
    assert isinstance(credentials, AzureConnectionStringSecret)
    assert credentials.scope is None
    assert credentials.connection_string.get_secret_value() == "sensitive"


@pytest.mark.parametrize("client_id", [None, "selected-identity"])
@pytest.mark.parametrize("scope", [None, "az://container/"])
def test_prefect_provider_translates_azure_managed_identity_block(
    client_id: str | None,
    scope: str | None,
) -> None:
    block = AzureManagedIdentityCredentials(
        account_name="storage",
        client_id=client_id,
        scope=scope,
    )

    with patch.object(
        AzureManagedIdentityCredentials, "load", return_value=block
    ) as load:
        credentials = PrefectCredentialProvider().resolve(
            "shared_identity",
            AzureManagedIdentitySecret,
        )

    load.assert_called_once_with("shared-identity")
    assert isinstance(credentials, AzureManagedIdentitySecret)
    assert credentials.account_name == "storage"
    assert credentials.client_id == client_id
    assert credentials.scope == scope


@pytest.mark.parametrize("fingerprint", [None, "SHA256:" + "A" * 43])
@pytest.mark.parametrize("model_type", [SshPrivateKeySecret, SftpFilesystem])
def test_prefect_provider_translates_ssh_private_key_block(
    fingerprint: str | None,
    model_type: type[SshPrivateKeySecret] | type[SftpFilesystem],
) -> None:
    block = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/sftp-key",
        port=2222,
        scope="sftp://sftp.example.test",
        host_key_fingerprint=fingerprint,
    )

    with patch.object(SshPrivateKeyCredentials, "load", return_value=block) as load:
        credentials = PrefectCredentialProvider().resolve("source_files", model_type)

    load.assert_called_once_with("source-files")
    assert isinstance(credentials, model_type)
    assert credentials.host_key_fingerprint == fingerprint
    resolved = credentials.resolve_overrides({"scope": "sftp://other.test"})
    assert resolved.host_key_fingerprint == fingerprint
    assert credentials.username.get_secret_value() == "reader"
    assert credentials.key_path == "/run/secrets/sftp-key"
    assert credentials.port == 2222
    assert credentials.scope == "sftp://sftp.example.test"


def test_prefect_provider_failure_does_not_include_underlying_error() -> None:
    with (
        patch.object(
            MssqlCredentials,
            "load",
            side_effect=RuntimeError("sensitive diagnostic"),
        ),
        pytest.raises(RuntimeError) as captured,
    ):
        PrefectCredentialProvider().resolve("shared-login", MssqlSecret)

    assert "shared-login" in str(captured.value)
    assert "sensitive diagnostic" not in str(captured.value)


def test_both_sql_functions_load_one_block_each_and_construct_the_requested_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    block = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/key",
        scope="sftp://files.example.test/",
    )
    provider = PrefectCredentialProvider()
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    before = block.model_dump()

    with (
        patch.object(SshPrivateKeyCredentials, "load", return_value=block) as load,
        patch.object(SshPrivateKeySecret, "register_duckdb_secret") as secret,
        patch.object(SftpFilesystem, "register_filesystem_protocol") as filesystem,
        duckdb.connect() as connection,
    ):
        install_functions(connection, ("register_secret", "register_filesystem"))
        assert connection.execute(
            "SELECT quackframe.register_secret('prefect', 'source_files', "
            "'ssh_private_key', overrides := MAP {'scope': 'sftp://other.test/'});"
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT quackframe.register_filesystem('prefect', 'source_files', 'sftp');"
        ).fetchone() == (True,)

    assert load.call_count == 2
    load.assert_called_with("source-files")
    secret.assert_called_once()
    filesystem.assert_called_once()
    assert block.model_dump() == before


def test_block_conversion_rejects_an_incompatible_model_family() -> None:
    block = SshPrivateKeyCredentials(
        username=SecretStr("reader"), key_path="/key", scope="sftp://files.test/"
    )
    with pytest.raises(ValueError, match="Incompatible"):
        block.to_credentials(MssqlSecret)

    model = block.to_credentials(SftpFilesystem)
    assert type(model) is SftpFilesystem
    assert model.username.get_secret_value() == "reader"
    assert model.key_path == "/key"
    assert model.port == 22
