"""Describe one Python function exposed through DuckDB SQL."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from importlib.util import find_spec
from inspect import Parameter, signature
from typing import Literal

from duckdb import DuckDBPyConnection

from quackframe.errors import FunctionDefinitionError, OptionalDependencyError

DuckDBNullHandling = Literal["default", "special"]
_FUNCTION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SqlFunction:
    """Describe one Python function that project SQL can call.

    The definition records the name and DuckDB options needed to install the
    function without coupling the installer to what that function does.
    """

    name: str
    callable: Callable[..., object]
    bind_connection: bool = False
    side_effects: bool = False
    null_handling: DuckDBNullHandling = "default"
    required_modules: tuple[str, ...] = ()

    @property
    def private_name(self) -> str:
        """Return the private Python name hidden behind the public SQL name."""

        return f"_quackframe_{self.name}"

    @property
    def sql_parameters(self) -> tuple[Parameter, ...]:
        """Return the Python parameters that SQL callers can provide.

        Connection-aware functions receive the active DuckDB connection from
        Quackframe, so their first Python parameter is not part of the public
        SQL arguments.
        """

        parameters = tuple(signature(self.callable).parameters.values())
        if self.bind_connection:
            # Quackframe supplies the active DuckDB connection itself. Remove
            # that first parameter so SQL callers can never provide it.
            if not parameters:
                raise FunctionDefinitionError(
                    f"Connection-bound function '{self.name}' has no parameters"
                )
            parameters = parameters[1:]

        unsupported = (
            Parameter.KEYWORD_ONLY,
            Parameter.VAR_POSITIONAL,
            Parameter.VAR_KEYWORD,
        )
        if any(parameter.kind in unsupported for parameter in parameters):
            raise FunctionDefinitionError(
                f"SQL function '{self.name}' cannot use keyword-only or "
                "variadic parameters"
            )

        optional_seen = False
        for parameter in parameters:
            optional = parameter.default is not Parameter.empty
            if optional and parameter.default is not None:
                raise FunctionDefinitionError(
                    f"Parameter '{parameter.name}' on '{self.name}' has an "
                    "unsupported default"
                )
            if not optional and optional_seen:
                raise FunctionDefinitionError(
                    f"Required parameter '{parameter.name}' follows an optional "
                    "parameter"
                )
            optional_seen = optional_seen or optional
        return parameters

    def validate(self) -> None:
        """Reject unsupported names, arguments, and required packages early."""

        if _FUNCTION_NAME.fullmatch(self.name) is None:
            raise FunctionDefinitionError(f"Invalid SQL function name: {self.name}")
        _ = self.sql_parameters
        for module_name in self.required_modules:
            if find_spec(module_name) is None:
                raise OptionalDependencyError(
                    f"SQL function '{self.name}' requires 'quackframe[{module_name}]'"
                )

    def bind(self, connection: DuckDBPyConnection) -> Callable[..., object]:
        """Inject the active connection when the function requests ownership."""

        if self.bind_connection:
            return partial(self.callable, connection)
        return self.callable

    def macro_sql(self) -> str:
        """Build the public SQL name that calls the private Python function.

        Only names created and checked by Quackframe enter this generated SQL.
        Values supplied during a run remain ordinary function arguments.
        """

        parameters = ",\n    ".join(
            _macro_parameter(parameter) for parameter in self.sql_parameters
        )
        arguments = ",\n    ".join(
            f'"{parameter.name}"' for parameter in self.sql_parameters
        )
        return (
            f'CREATE OR REPLACE MACRO "quackframe"."{self.name}"(\n'
            f"    {parameters}\n"
            f') AS "{self.private_name}"(\n'
            f"    {arguments}\n"
            ")"
        )


def _macro_parameter(parameter: Parameter) -> str:
    """Write one validated parameter for the public DuckDB function."""

    rendered = f'"{parameter.name}"'
    if parameter.default is None:
        return f"{rendered} := NULL"
    return rendered
