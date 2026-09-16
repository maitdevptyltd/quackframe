"""Generic SQL-function registration tests."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from duckdb import DuckDBPyConnection

from quackframe import FunctionsConfig, QuackframeConfig, run
from quackframe.errors import ConfigurationError, FunctionDefinitionError
from quackframe.sql_functions import registry
from quackframe.sql_functions.definition import SqlFunction


def echo(value: str) -> str:
    return value


def connection_label(
    connection: DuckDBPyConnection,
    value: str,
    suffix: str | None = None,
) -> str:
    assert isinstance(connection, DuckDBPyConnection)
    return value + (suffix or "")


def map_value(values: dict[str, str] | None = None) -> str:
    return (values or {}).get("key", "missing")


def invalid_default(value: str = "value") -> str:
    return value


@pytest.fixture
def function_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        registry,
        "BUILTIN_FUNCTIONS",
        (
            SqlFunction(name="echo", callable=echo),
            SqlFunction(
                name="connection_label",
                callable=connection_label,
                bind_connection=True,
                null_handling="special",
            ),
            SqlFunction(
                name="map_value",
                callable=map_value,
                null_handling="special",
            ),
        ),
    )


def test_registrar_supports_pure_connection_bound_and_optional_functions(
    tmp_path: Path,
    function_registry: None,
) -> None:
    sql_file = tmp_path / "functions.sql"
    sql_file.write_text(
        """
CREATE TABLE answers AS
SELECT
    quackframe.echo('value') AS echoed,
    quackframe.connection_label('value', suffix := '-bound') AS bound,
    quackframe.map_value(MAP {'key': 'mapped'}) AS mapped;
""".strip(),
        encoding="utf-8",
    )
    database_path = tmp_path / "functions.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": tmp_path,
            "database": {"mode": "persistent", "path": database_path},
            "functions": {"enabled": ["echo", "connection_label", "map_value"]},
        }
    )

    run([sql_file], config=config)

    with duckdb.connect(str(database_path)) as connection:
        assert connection.execute("SELECT * FROM answers").fetchone() == (
            "value",
            "value-bound",
            "mapped",
        )


def test_unknown_enabled_function_fails_before_sql(tmp_path: Path) -> None:
    sql_file = tmp_path / "not-run.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    config = QuackframeConfig(
        root=tmp_path,
        functions=FunctionsConfig(enabled=("unknown",)),
    )

    with pytest.raises(ConfigurationError, match="Unknown enabled SQL function"):
        run([sql_file], config=config)


def test_unsupported_default_fails_definition_validation() -> None:
    definition = SqlFunction(name="invalid_default", callable=invalid_default)

    with pytest.raises(FunctionDefinitionError, match="unsupported default"):
        definition.validate()


def test_connection_is_bound_outside_sql_signature() -> None:
    definition = SqlFunction(
        name="connection_label",
        callable=connection_label,
        bind_connection=True,
    )

    assert tuple(parameter.name for parameter in definition.sql_parameters) == (
        "value",
        "suffix",
    )

    with duckdb.connect() as connection:
        bound_function = definition.bind(connection)
        assert bound_function("value", "-bound") == "value-bound"
