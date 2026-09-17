"""Optional Prefect runtime and Block provider tests."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import SecretStr

prefect = pytest.importorskip("prefect")

from prefect.testing.utilities import prefect_test_harness  # noqa: E402

from quackframe import QuackframeConfig, run  # noqa: E402
from quackframe.integrations.prefect import runtime as prefect_runtime  # noqa: E402
from quackframe.sql import PreparedSqlFile  # noqa: E402
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    AzureConnectionStringCredentials as ResolvedAzureCredentials,
)
from quackframe.sql_functions.register_secret.models import (  # noqa: E402
    MssqlCredentials as ResolvedMssqlCredentials,
)
from quackframe.sql_functions.register_secret.providers.prefect.blocks import (  # noqa: E402
    AzureConnectionStringCredentials,
    MssqlCredentials,
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


def test_prefect_flow_has_a_stable_name() -> None:
    assert prefect_runtime.execute_plan_flow.name == "quackframe-run"


def test_prefect_file_task_uses_the_path_stem(tmp_path: Path) -> None:
    task_call = Mock()
    sql_file = PreparedSqlFile(path=tmp_path / "01-load-data.sql")

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
    task_call.assert_called_once()


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

    with patch.object(MssqlCredentials, "load", return_value=block):
        credentials = PrefectCredentialProvider().resolve("shared-login", "mssql")

    assert isinstance(credentials, ResolvedMssqlCredentials)
    assert credentials.database is None
    assert credentials.password.get_secret_value() == "sensitive"


def test_prefect_provider_translates_azure_block() -> None:
    block = AzureConnectionStringCredentials(connection_string=SecretStr("sensitive"))

    with patch.object(AzureConnectionStringCredentials, "load", return_value=block):
        credentials = PrefectCredentialProvider().resolve(
            "shared-storage",
            "azure_connection_string",
        )

    assert isinstance(credentials, ResolvedAzureCredentials)
    assert credentials.scope is None
    assert credentials.connection_string.get_secret_value() == "sensitive"


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
