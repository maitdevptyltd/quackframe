"""Errors shared by every way of running Quackframe."""

from pathlib import Path

import duckdb


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
    """Describe external failures without copying their potentially sensitive text."""

    # Even the first diagnostic line can contain query values or credentials.
    # Only known exception types select messages; unknown errors stay generic.
    reasons: dict[type[Exception], str] = {
        duckdb.ParserException: "SQL syntax is invalid",
        duckdb.BinderException: "SQL names or types could not be resolved",
        duckdb.CatalogException: "A database object could not be resolved",
        duckdb.ConversionException: (
            "A value could not be converted to the required type"
        ),
        duckdb.ConstraintException: "A database constraint was violated",
        duckdb.IOException: "A database input/output operation failed",
        duckdb.OutOfMemoryException: "DuckDB ran out of memory",
        duckdb.TransactionException: "A database transaction failed",
        duckdb.InvalidInputException: "DuckDB rejected an input or extension operation",
    }
    return reasons.get(type(error), "The operation failed")
