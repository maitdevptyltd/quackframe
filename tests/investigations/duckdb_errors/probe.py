"""Offline DuckDB diagnostic probes; all values and files are synthetic."""

from __future__ import annotations

import json
import platform
import sys
import tempfile
import traceback
from contextlib import chdir
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import duckdb


@dataclass(frozen=True)
class Scenario:
    id: str
    source: str
    sql: str
    setup: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    action: str = "execute"
    anchor: str = ""


SCENARIOS = (
    Scenario(
        "parser_literal",
        "literal",
        "SELECT 'FAKE_LITERAL_SECRET' + FROM x",
        anchor="FROM",
    ),
    Scenario(
        "parser_token",
        "identifier",
        "SELECT 1 AS x FAKE_IDENTIFIER_PRIVATE",
        anchor="FAKE_IDENTIFIER_PRIVATE",
    ),
    Scenario(
        "parser_multiline",
        "literal",
        "SELECT\n 'FAKE_LITERAL_SECRET',\n FROM",
        anchor="FROM",
    ),
    Scenario(
        "parser_path",
        "path",
        "SELECT '/FAKE_PATH_PRIVATE/file.csv' + FROM x",
        anchor="FROM",
    ),
    Scenario(
        "parser_path_token",
        "path",
        "SELECT 1 '/FAKE_PATH_PRIVATE/file.csv'",
        anchor="'/FAKE_PATH_PRIVATE/file.csv'",
    ),
    Scenario(
        "binder_key_literal",
        "literal",
        "SELECT struct_extract({'a':1}, 'FAKE_LITERAL_SECRET')",
    ),
    Scenario(
        "catalog_path_identifier",
        "path",
        'SELECT "FAKE_PATH_PRIVATE/file.csv"()',
    ),
    Scenario(
        "binder_literal",
        "literal",
        "SELECT absent, 'FAKE_LITERAL_SECRET'",
        anchor="absent",
    ),
    Scenario(
        "binder_candidates",
        "candidate",
        "SELECT missing FROM t",
        ("CREATE TABLE t(FAKE_CANDIDATE_PRIVATE INT)",),
        anchor="missing",
    ),
    Scenario(
        "catalog_identifier",
        "identifier",
        "SELECT * FROM FAKE_IDENTIFIER_PRIVATE",
        anchor="FAKE_IDENTIFIER_PRIVATE",
    ),
    Scenario(
        "catalog_literal",
        "literal",
        "SELECT 'FAKE_LITERAL_SECRET' FROM absent",
        anchor="absent",
    ),
    Scenario(
        "catalog_candidates",
        "candidate",
        "SELECT * FROM FAKE_CANDIDATE_PRIVAT",
        ("CREATE TABLE FAKE_CANDIDATE_PRIVATE(i INT)",),
    ),
    Scenario(
        "conversion_literal",
        "literal",
        "SELECT CAST('FAKE_LITERAL_SECRET' AS INTEGER)",
        anchor="CAST",
    ),
    Scenario(
        "conversion_parameter",
        "parameter",
        "SELECT CAST(? AS INTEGER)",
        parameters=("FAKE_PARAMETER_SECRET",),
        anchor="CAST",
    ),
    Scenario(
        "conversion_row",
        "row",
        "SELECT CAST(v AS INTEGER) FROM t",
        ("CREATE TABLE t(v VARCHAR)", "INSERT INTO t VALUES ('FAKE_ROW_PERSONAL')"),
        anchor="CAST",
    ),
    Scenario(
        "constraint_row",
        "row",
        "INSERT INTO target SELECT v FROM source",
        (
            "CREATE TABLE source(v VARCHAR)",
            "INSERT INTO source VALUES ('FAKE_ROW_BUSINESS')",
            "CREATE TABLE target(v VARCHAR UNIQUE)",
            "INSERT INTO target SELECT v FROM source",
        ),
    ),
    Scenario(
        "check_row",
        "row",
        "INSERT INTO target SELECT v FROM source",
        (
            "CREATE TABLE source(v VARCHAR)",
            "INSERT INTO source VALUES ('FAKE_ROW_PERSONAL')",
            "CREATE TABLE target(v VARCHAR CHECK(length(v)<2))",
        ),
    ),
    Scenario("custom_literal", "custom", "SELECT error('FAKE_CUSTOM_SECRET')"),
    Scenario(
        "custom_row",
        "row",
        "SELECT error(v) FROM t",
        ("CREATE TABLE t(v VARCHAR)", "INSERT INTO t VALUES ('FAKE_ROW_PERSONAL')"),
    ),
    Scenario(
        "custom_connection_string",
        "connection string",
        "SELECT error(?)",
        parameters=("Host=FAKE_HOST_PRIVATE;Password=FAKE_CONNECTION_SECRET",),
    ),
    Scenario(
        "udf_message",
        "upstream",
        "SELECT upstream(v) FROM t",
        ("CREATE TABLE t(v VARCHAR)", "INSERT INTO t VALUES ('FAKE_ROW_PERSONAL')"),
        action="udf",
    ),
    Scenario(
        "python_chain",
        "cause/context",
        "SELECT CAST(? AS INTEGER)",
        parameters=("FAKE_PARAMETER_SECRET",),
        action="chain",
    ),
    Scenario(
        "missing_file",
        "path",
        "SELECT * FROM read_csv('FAKE_PATH_PRIVATE/missing.csv')",
        anchor="read_csv",
    ),
    Scenario(
        "url_blocked",
        "URL",
        "SELECT * FROM read_csv('https://FAKE_HOST_PRIVATE.invalid/file?token=FAKE_URL_TOKEN')",
        action="external_disabled",
        anchor="read_csv",
    ),
    Scenario(
        "csv_row",
        "file row",
        "SELECT * FROM read_csv('FAKE_PATH_PRIVATE.csv', "
        "columns={'v':'INTEGER'}, header=true)",
        action="csv",
        anchor="read_csv",
    ),
    Scenario(
        "parquet_invalid",
        "path/file",
        "SELECT * FROM read_parquet('FAKE_PATH_PRIVATE.parquet')",
        action="parquet",
        anchor="read_parquet",
    ),
    Scenario(
        "json_row",
        "row",
        "SELECT CAST(v AS JSON) FROM t",
        ("CREATE TABLE t(v VARCHAR)", "INSERT INTO t VALUES ('FAKE_ROW_PERSONAL')"),
    ),
    Scenario(
        "regex_parameter",
        "parameter",
        "SELECT regexp_matches('x', ?)",
        parameters=("[FAKE_PARAMETER_SECRET",),
    ),
    Scenario(
        "range",
        "numeric row",
        "SELECT v + 1 FROM t",
        ("CREATE TABLE t(v BIGINT)", "INSERT INTO t VALUES (9223372036854775807)"),
    ),
    Scenario("transaction", "identifier", "BEGIN TRANSACTION", ("BEGIN TRANSACTION",)),
    Scenario(
        "dependency",
        "identifier",
        "DROP TABLE FAKE_IDENTIFIER_PRIVATE",
        (
            "CREATE TABLE FAKE_IDENTIFIER_PRIVATE(i INT PRIMARY KEY)",
            "CREATE TABLE child(i INT REFERENCES FAKE_IDENTIFIER_PRIVATE(i))",
        ),
    ),
    Scenario(
        "not_implemented",
        "identifier",
        "ALTER TABLE t ADD CONSTRAINT FAKE_IDENTIFIER_PRIVATE UNIQUE(i)",
        ("CREATE TABLE t(i INT)",),
    ),
    Scenario(
        "sequence",
        "identifier",
        "SELECT nextval('FAKE_IDENTIFIER_PRIVATE')",
        (
            "CREATE SEQUENCE FAKE_IDENTIFIER_PRIVATE MAXVALUE 2 START 2",
            "SELECT nextval('FAKE_IDENTIFIER_PRIVATE')",
        ),
    ),
    Scenario(
        "closed_connection",
        "connection",
        "SELECT 'FAKE_LITERAL_SECRET'",
        action="closed",
    ),
    Scenario("parameter_missing", "parameter name", "SELECT $FAKE_PARAMETER_NAME"),
    Scenario("setting", "setting value", "SET threads='FAKE_SETTING_PRIVATE'"),
    Scenario(
        "extension_missing",
        "extension path",
        "LOAD 'FAKE_PATH_PRIVATE.duckdb_extension'",
    ),
    Scenario(
        "pivot_conversion",
        "row",
        "PIVOT t ON category USING sum(CAST(v AS INTEGER))",
        (
            "CREATE TABLE t(category VARCHAR, v VARCHAR)",
            "INSERT INTO t VALUES ('group_a','FAKE_ROW_PERSONAL')",
        ),
        anchor="CAST",
    ),
    Scenario(
        "pivot_candidate",
        "row-derived identifier",
        "SELECT missing FROM (PIVOT t ON category USING sum(v))",
        (
            "CREATE TABLE t(category VARCHAR, v INT)",
            "INSERT INTO t VALUES ('FAKE_ROW_BUSINESS',1)",
        ),
        anchor="missing",
    ),
    Scenario(
        "multiline_binder",
        "literal",
        "SELECT\n 'FAKE_LITERAL_SECRET',\n absent",
        anchor="absent",
    ),
    Scenario(
        "unicode_position",
        "literal",
        "SELECT 'éFAKE_LITERAL_SECRET', absent",
        anchor="absent",
    ),
    Scenario(
        "extract_parser",
        "literal",
        "SELECT 'FAKE_LITERAL_SECRET' + FROM x",
        action="extract",
        anchor="FROM",
    ),
)

MARKERS = (
    "FAKE_LITERAL_SECRET",
    "FAKE_IDENTIFIER_PRIVATE",
    "FAKE_PATH_PRIVATE",
    "FAKE_CANDIDATE_PRIVATE",
    "FAKE_PARAMETER_SECRET",
    "FAKE_ROW_PERSONAL",
    "FAKE_ROW_BUSINESS",
    "FAKE_CUSTOM_SECRET",
    "FAKE_HOST_PRIVATE",
    "FAKE_CONNECTION_SECRET",
    "FAKE_UPSTREAM_SECRET",
    "FAKE_CAUSE_SECRET",
    "FAKE_CONTEXT_SECRET",
    "FAKE_URL_TOKEN",
    "FAKE_PARAMETER_NAME",
    "FAKE_SETTING_PRIVATE",
    "9223372036854775807",
)


def upstream(value: str) -> str:
    raise ValueError("FAKE_UPSTREAM_SECRET: " + value)


def execute(connection: duckdb.DuckDBPyConnection, scenario: Scenario) -> None:
    if scenario.action == "extract":
        connection.extract_statements(scenario.sql)
    else:
        connection.execute(scenario.sql, scenario.parameters or None).fetchall()


def capture(error: BaseException) -> dict[str, Any]:
    message = str(error)
    # Some Python exception classes retain a prefix before the JSON object.
    offset = message.find("{")
    try:
        structured = json.loads(message[offset:]) if offset >= 0 else None
    except json.JSONDecodeError:
        structured = None
    return {
        "class": type(error).__name__,
        "message": message,
        "repr": repr(error),
        "args": repr(error.args),
        "structured": structured,
        "traceback": "".join(traceback.format_exception(error)),
        "cause": capture(error.__cause__) if error.__cause__ else None,
        "context": capture(error.__context__) if error.__context__ else None,
        "suppress_context": error.__suppress_context__,
    }


def marker_surfaces(value: Any, path: str = "exception") -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            result.update(marker_surfaces(item, f"{path}.{key}"))
    elif isinstance(value, str):
        # Binder/catalog diagnostics may normalize identifiers to lowercase.
        found = [marker for marker in MARKERS if marker.casefold() in value.casefold()]
        if found:
            result[path] = found
    return result


def probe(scenario: Scenario, json_mode: bool) -> dict[str, Any]:
    with (
        tempfile.TemporaryDirectory(prefix="duckdb-error-probe-") as temporary,
        chdir(temporary),
    ):
        # Relative fixture names make diagnostics comparable across machines.
        connection = duckdb.connect(
            config={
                "autoinstall_known_extensions": "false",
                "autoload_known_extensions": "false",
                "threads": "1",
                "memory_limit": "128MB",
                "max_temp_directory_size": "0B",
            }
        )
        connection.execute(f"SET errors_as_json = {str(json_mode).lower()}")
        for statement in scenario.setup:
            connection.execute(statement)
        if scenario.action == "csv":
            Path("FAKE_PATH_PRIVATE.csv").write_text(
                "v\nFAKE_ROW_PERSONAL\n", encoding="utf-8"
            )
        elif scenario.action == "parquet":
            Path("FAKE_PATH_PRIVATE.parquet").write_bytes(b"FAKE_ROW_BUSINESS")
        elif scenario.action == "udf":
            # DuckDB's Arrow overload has an unknown return in its shipped stub.
            connection.create_function("upstream", upstream)  # pyright: ignore[reportUnknownMemberType]
        elif scenario.action == "external_disabled":
            connection.execute("SET enable_external_access=false")
        elif scenario.action == "closed":
            connection.close()

        observed: dict[str, Any] | None = None
        try:
            if scenario.action == "chain":
                try:
                    execute(connection, scenario)
                except duckdb.Error as backend:
                    try:
                        raise ValueError("FAKE_CONTEXT_SECRET") from backend
                    except ValueError as wrapper:
                        raise RuntimeError("FAKE_CAUSE_SECRET") from wrapper
            else:
                execute(connection, scenario)
        except Exception as error:
            observed = capture(error)
        finally:
            connection.close()

        result: dict[str, Any] = {
            "scenario": asdict(scenario),
            "json_mode": json_mode,
            "status": "error_observed" if observed else "no_error",
            "exception": observed,
            "marker_surfaces": marker_surfaces(observed),
            "anchor_character_offset": scenario.sql.find(scenario.anchor)
            if scenario.anchor
            else None,
            "anchor_utf8_offset": len(scenario.sql.split(scenario.anchor)[0].encode())
            if scenario.anchor
            else None,
            "runtime": {
                "duckdb": duckdb.__version__,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
        }
        # Only machine-specific fixture/harness paths are normalized; diagnostics
        # and marker occurrences otherwise remain verbatim, including line numbers.
        serialized = json.dumps(result, ensure_ascii=False)
        for original, replacement in (
            (temporary, "<fixture>"),
            (str(Path(__file__).resolve()), "<probe.py>"),
        ):
            escaped = original
            variants: list[str] = []
            for _ in range(4):
                escaped = json.dumps(escaped)[1:-1]
                variants.append(escaped)
            for variant in reversed(variants):
                serialized = serialized.replace(variant, replacement)
        return json.loads(serialized)


if __name__ == "__main__":
    selected = next(item for item in SCENARIOS if item.id == sys.argv[1])
    print(json.dumps(probe(selected, sys.argv[2] == "json"), ensure_ascii=True))
