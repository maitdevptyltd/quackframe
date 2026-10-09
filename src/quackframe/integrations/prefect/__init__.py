"""Optional Prefect runtime integration."""

from quackframe.errors import OptionalDependencyError

try:
    from quackframe.integrations.prefect.runtime import quackframe_flow
except ModuleNotFoundError as error:
    if error.name == "prefect" or (
        error.name is not None and error.name.startswith("prefect.")
    ):
        raise OptionalDependencyError(
            "The Prefect runtime requires 'quackframe[prefect]'"
        ) from None
    raise

__all__ = ["quackframe_flow"]
