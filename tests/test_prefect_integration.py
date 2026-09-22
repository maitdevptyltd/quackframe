"""Optional Prefect runtime and Block provider tests."""

from pathlib import Path
from unittest.mock import ANY, Mock, patch

import duckdb
import pytest
from pydantic import SecretStr

prefect = pytest.importorskip("prefect")

from prefect.testing.utilities import prefect_test_harness  # noqa: E402

from quackframe import QuackframeConfig, load_config, run  # noqa: E402
from quackframe.integrations.prefect import runtime as prefect_runtime  # noqa: E402
from quackframe.sql import PreparedSqlFile, prepare_sql_files  # noqa: E402
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    AzureConnectionStringCredentials as ResolvedAzureCredentials,
)
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    MssqlCredentials as ResolvedMssqlCredentials,
)
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    SshPrivateKeyCredentials as ResolvedSshPrivateKeyCredentials,
)
from quackframe.sql_functions.register_secret.providers.prefect.blocks import (  # noqa: E402
    AzureConnectionStringCredentials,
    MssqlCredentials,
    SshPrivateKeyCredentials,
)
from quackframe.sql_functions.register_secret.providers.prefect.provider import (  # noqa: E402
    PrefectCredentialProvider,
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


def test_prefect_provider_rejects_unknown_secret_type_explicitly() -> None:
    with pytest.raises(ValueError, match="Unsupported Prefect secret type"):
        PrefectCredentialProvider().resolve(
            "shared-secret",
            "future_type",
        )


def test_prefect_provider_translates_mssql_block() -> None:
    block = MssqlCredentials(
        host="sql.example.test",
        user=SecretStr("reader"),
        password=SecretStr("sensitive"),
    )

    with patch.object(MssqlCredentials, "load", return_value=block) as load:
        credentials = PrefectCredentialProvider().resolve("shared_login", "mssql")

    load.assert_called_once_with("shared-login")
    assert isinstance(credentials, ResolvedMssqlCredentials)
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
            "azure_connection_string",
        )

    load.assert_called_once_with("shared-storage")
    assert isinstance(credentials, ResolvedAzureCredentials)
    assert credentials.scope is None
    assert credentials.connection_string.get_secret_value() == "sensitive"


def test_prefect_provider_translates_ssh_private_key_block() -> None:
    block = SshPrivateKeyCredentials(
        username=SecretStr("reader"),
        key_path="/run/secrets/sftp-key",
        port=2222,
        scope="sftp://sftp.example.test",
    )

    with patch.object(SshPrivateKeyCredentials, "load", return_value=block) as load:
        credentials = PrefectCredentialProvider().resolve(
            "source_files", "ssh_private_key"
        )

    load.assert_called_once_with("source-files")
    assert isinstance(credentials, ResolvedSshPrivateKeyCredentials)
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
        PrefectCredentialProvider().resolve("shared-login", "mssql")

    assert "shared-login" in str(captured.value)
    assert "sensitive diagnostic" not in str(captured.value)
