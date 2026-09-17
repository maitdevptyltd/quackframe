"""Install enabled Python functions in DuckDB."""

from __future__ import annotations

import types
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

import duckdb
from duckdb import DuckDBPyConnection
from duckdb.func import FunctionNullHandling
from duckdb.sqltypes import BIGINT, BOOLEAN, DOUBLE, VARCHAR

from quackframe.errors import FunctionDefinitionError, safe_error_reason
from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.registry import resolve_functions

_DUCKDB_SCALAR_TYPES: dict[Any, Any] = {
    str: VARCHAR,
    bool: BOOLEAN,
    int: BIGINT,
    float: DOUBLE,
}


def install_functions(
    connection: DuckDBPyConnection,
    enabled_names: tuple[str, ...],
) -> None:
    """Install every enabled function through the same shared path.

    Definitions and signatures are validated before DuckDB catalog changes
    begin. The schema, private Python functions, and public SQL names are then
    installed together so a failure cannot leave a half-installed interface.
    """

    definitions = resolve_functions(enabled_names)
    prepared: list[tuple[SqlFunction, list[Any], Any]] = []
    for definition in definitions:
        definition.validate()
        parameter_types, return_type = _duckdb_signature(definition)
        prepared.append((definition, parameter_types, return_type))

    try:
        connection.execute("BEGIN TRANSACTION")
        connection.execute('CREATE SCHEMA IF NOT EXISTS "quackframe"')
        for definition, parameter_types, return_type in prepared:
            # Quackframe supplies the connection to functions that need it.
            # SQL callers see only the remaining, ordinary arguments.
            connection.create_function(  # pyright: ignore[reportUnknownMemberType]
                definition.private_name,
                definition.bind(connection),
                parameters=parameter_types,
                return_type=return_type,
                side_effects=definition.side_effects,
                null_handling=cast(FunctionNullHandling, definition.null_handling),
            )
            connection.execute(definition.macro_sql())
        connection.execute("COMMIT")
    except Exception as error:
        connection.execute("ROLLBACK")
        raise FunctionDefinitionError(
            f"SQL functions could not be installed: {safe_error_reason(error)}"
        ) from None


def _duckdb_signature(
    definition: SqlFunction,
) -> tuple[list[Any], Any]:
    """Read a Python function's type hints and return its DuckDB types."""

    try:
        hints = get_type_hints(definition.callable)
    except (NameError, TypeError) as error:
        raise FunctionDefinitionError(
            f"Could not resolve type annotations for '{definition.name}': {error}"
        ) from None

    parameters: list[Any] = []
    for parameter in definition.sql_parameters:
        annotation = hints.get(parameter.name)
        if annotation is None:
            raise FunctionDefinitionError(
                f"Parameter '{parameter.name}' on '{definition.name}' needs a "
                "type annotation"
            )
        parameters.append(_duckdb_type(annotation, definition.name))

    return_annotation = hints.get("return")
    if return_annotation is None:
        raise FunctionDefinitionError(
            f"SQL function '{definition.name}' needs a return type annotation"
        )
    return parameters, _duckdb_type(return_annotation, definition.name)


def _duckdb_type(annotation: Any, function_name: str) -> Any:
    """Map one supported Python type hint to the matching DuckDB type."""

    annotation = _without_none(annotation)
    if annotation in _DUCKDB_SCALAR_TYPES:
        return _DUCKDB_SCALAR_TYPES[annotation]

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is dict and arguments == (str, str):
        return duckdb.map_type(VARCHAR, VARCHAR)

    raise FunctionDefinitionError(
        f"SQL function '{function_name}' uses unsupported type annotation: "
        f"{annotation!r}"
    )


def _without_none(annotation: Any) -> Any:
    """Return the value type from a ``value | None`` type hint."""

    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        arguments = tuple(
            argument for argument in get_args(annotation) if argument is not type(None)
        )
        if len(arguments) == 1:
            return arguments[0]
    return annotation
