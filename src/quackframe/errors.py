"""Errors shared by every way of running Quackframe."""

from pathlib import Path


class QuackframeError(RuntimeError):
    """Identify an actionable failure produced by Quackframe."""


class ConfigurationError(QuackframeError):
    """Report configuration that could not be resolved or validated."""


class FunctionDefinitionError(ConfigurationError):
    """Report a SQL-callable function that cannot be installed safely."""


class OptionalDependencyError(ConfigurationError):
    """Explain which package is required by a selected optional capability."""


class ExecutionError(QuackframeError):
    """Report SQL failure with safe file and statement context.

    The exception intentionally omits full SQL text and returned query data.
    """

    def __init__(
        self,
        *,
        sql_file: Path,
        reason: str,
        statement_number: int | None = None,
    ) -> None:
        """Build a safe message for one failed file and optional statement."""

        self.sql_file = sql_file
        self.statement_number = statement_number
        self.reason = reason

        location = str(sql_file)
        if statement_number is not None:
            location = f"{location}, statement {statement_number}"
        super().__init__(f"SQL execution failed in {location}: {reason}")


def safe_error_reason(error: Exception) -> str:
    """Keep the first external-error line without returning a large payload.

    Callers must still avoid passing exceptions whose first line contains
    credential values; provider boundaries replace such errors entirely.
    """

    message = str(error).strip()
    if not message:
        return error.__class__.__name__
    return message.splitlines()[0][:300]
