"""Framework-independent Quackframe exceptions."""

from pathlib import Path


class QuackframeError(RuntimeError):
    """Base class for actionable Quackframe failures."""


class ConfigurationError(QuackframeError):
    """Configuration could not be resolved or validated."""


class FunctionDefinitionError(ConfigurationError):
    """A SQL-callable function has an unsupported definition."""


class OptionalDependencyError(ConfigurationError):
    """A selected capability needs an optional dependency."""


class ExecutionError(QuackframeError):
    """SQL execution failed with safe file and statement context."""

    def __init__(
        self,
        *,
        sql_file: Path,
        reason: str,
        statement_number: int | None = None,
    ) -> None:
        self.sql_file = sql_file
        self.statement_number = statement_number
        self.reason = reason

        location = str(sql_file)
        if statement_number is not None:
            location = f"{location}, statement {statement_number}"
        super().__init__(f"SQL execution failed in {location}: {reason}")


def safe_error_reason(error: Exception) -> str:
    """Keep an external error useful without returning its detailed payload."""

    message = str(error).strip()
    if not message:
        return error.__class__.__name__
    return message.splitlines()[0][:300]
