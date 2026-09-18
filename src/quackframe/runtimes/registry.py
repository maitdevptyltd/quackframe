"""Describe and load the runtime adapters available to Quackframe."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from quackframe.errors import OptionalDependencyError
from quackframe.models import ExecutionResult

if TYPE_CHECKING:
    from quackframe.config import QuackframeConfig
    from quackframe.sql import PreparedSqlFile


class Runtime(Protocol):
    """Run prepared SQL files without changing Quackframe's normal behaviour."""

    def __call__(
        self,
        sql_files: tuple[PreparedSqlFile, ...],
        config: QuackframeConfig,
    ) -> ExecutionResult:
        """Run the files in order and return a standard Quackframe result."""

        ...


@dataclass(frozen=True)
class RuntimeRegistration:
    """Describe one runtime and how Quackframe loads its code.

    Optional runtimes name the package they need so Quackframe can explain how
    to install it instead of returning a raw import error.
    """

    name: str
    module_name: str
    implementation_name: str
    result_logging_is_external: bool
    missing_dependency: str | None = None
    missing_dependency_message: str | None = None

    def load(self) -> Runtime:
        """Import the runtime only after configuration selects its public name."""

        # Keeping module paths as registry data delays optional framework
        # imports until the caller actually selects that runtime.
        try:
            module = import_module(self.module_name)
        except ModuleNotFoundError as error:
            dependency = self.missing_dependency
            if dependency is not None and (
                error.name == dependency
                or (error.name is not None and error.name.startswith(f"{dependency}."))
            ):
                raise OptionalDependencyError(
                    self.missing_dependency_message
                    or f"Runtime '{self.name}' requires the '{dependency}' package"
                ) from None
            raise

        return cast(Runtime, getattr(module, self.implementation_name))


RUNTIME_REGISTRY: tuple[RuntimeRegistration, ...] = (
    RuntimeRegistration(
        name="direct",
        module_name="quackframe.engine",
        implementation_name="execute_plan",
        result_logging_is_external=False,
    ),
    RuntimeRegistration(
        name="prefect",
        module_name="quackframe.integrations.prefect.runtime",
        implementation_name="execute_with_prefect",
        result_logging_is_external=True,
        missing_dependency="prefect",
        missing_dependency_message=(
            "The Prefect runtime requires 'quackframe[prefect]'"
        ),
    ),
)


def runtime_names() -> tuple[str, ...]:
    """Return the public runtime names accepted by configuration and the CLI."""

    return tuple(registration.name for registration in RUNTIME_REGISTRY)


def get_runtime(name: str) -> Runtime:
    """Load the runtime registered under ``name``.

    The registry is the only place that connects a public runtime name to an
    implementation, so adding an adapter does not require new selection
    branches in configuration or command-line code.
    """

    return get_runtime_registration(name).load()


def get_runtime_registration(name: str) -> RuntimeRegistration:
    """Return the adapter registration that owns runtime policy and loading."""

    for registration in RUNTIME_REGISTRY:
        if registration.name == name:
            return registration
    raise OptionalDependencyError(f"Unsupported runtime: {name}")
