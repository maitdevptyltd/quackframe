"""Explicit registry of built-in SQL functions."""

from quackframe.errors import ConfigurationError
from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.register_secret import register_secret_function

BUILTIN_FUNCTIONS: tuple[SqlFunction, ...] = (register_secret_function,)


def resolve_functions(enabled_names: tuple[str, ...]) -> tuple[SqlFunction, ...]:
    """Return the built-in functions explicitly enabled by the project.

    Installation never scans packages, so adding code cannot silently expose a
    new SQL capability to downstream projects.
    """

    if len(set(enabled_names)) != len(enabled_names):
        raise ConfigurationError("Enabled SQL function names must be unique")

    available = {definition.name: definition for definition in BUILTIN_FUNCTIONS}
    unknown = tuple(name for name in enabled_names if name not in available)
    if unknown:
        joined = ", ".join(unknown)
        raise ConfigurationError(f"Unknown enabled SQL function(s): {joined}")
    return tuple(available[name] for name in enabled_names)
