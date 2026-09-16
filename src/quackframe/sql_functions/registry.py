"""Explicit registry of built-in SQL functions."""

from quackframe.errors import ConfigurationError
from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.register_secret import register_secret_function

BUILTIN_FUNCTIONS: tuple[SqlFunction, ...] = (register_secret_function,)


def resolve_functions(enabled_names: tuple[str, ...]) -> tuple[SqlFunction, ...]:
    """Resolve the project allowlist against the reviewable built-in registry."""

    if len(set(enabled_names)) != len(enabled_names):
        raise ConfigurationError("Enabled SQL function names must be unique")

    available = {definition.name: definition for definition in BUILTIN_FUNCTIONS}
    unknown = tuple(name for name in enabled_names if name not in available)
    if unknown:
        joined = ", ".join(unknown)
        raise ConfigurationError(f"Unknown enabled SQL function(s): {joined}")
    return tuple(available[name] for name in enabled_names)
