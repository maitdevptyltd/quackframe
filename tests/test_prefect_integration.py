"""Optional Prefect runtime and Block provider tests."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr

prefect = pytest.importorskip("prefect")

from prefect.testing.utilities import prefect_test_harness  # noqa: E402

from quackframe import QuackframeConfig, run  # noqa: E402
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
