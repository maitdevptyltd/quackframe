"""Errors shared by every way of running Quackframe."""

import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit, urlunsplit

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
    """Report SQL failure with file and statement context.

    The selected runtime policy determines whether backend details are included.
    """

    def __init__(
        self,
        *,
        sql_file: Path,
        reason: str,
        statement_number: int | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        """Build a safe message for one failed file and optional statement."""

        self.sql_file = sql_file
        self.statement_number = statement_number
        self.reason = reason
        self.line = line
        self.column = column

        location = str(sql_file)
        if statement_number is not None:
            location = f"{location}, statement {statement_number}"
        if line is not None:
            location += f", line {line}"
            if column is not None:
                location += f", column {column}"
        super().__init__(f"SQL execution failed in {location}: {reason}")


def error_reason(error: Exception, *, include_details: bool) -> str:
    """Select full backend diagnostics only for an authorised destination."""

    if not include_details:
        return safe_error_reason(error)
    details = error_details(error)
    if "exception_message" in details:
        category = details.get("exception_type", type(error).__name__)
        return f"{category}: {details['exception_message']}"
    return str(error)


def safe_error_reason(error: Exception) -> str:
    """Describe external failures without copying their potentially sensitive text."""

    details = error_details(error)
    reason = _diagnostic_reason(details)
    if reason:
        return f"{details['exception_type']}: {reason}"

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
    reason = reasons.get(type(error))
    if reason:
        return f"{type(error).__name__}: {reason}"
    if isinstance(error, duckdb.Error):
        return f"{type(error).__name__}: The database operation failed"
    return "The operation failed"


def error_details(error: Exception) -> dict[str, str]:
    """Read DuckDB's structured payload, never arbitrary upstream exceptions."""

    if not isinstance(error, duckdb.Error):
        return {}
    text = str(error)
    start = text.find("{")
    if start < 0:
        # The relation API returns text for some binder/catalog failures even
        # with errors_as_json enabled. Extract only the same supported metadata.
        if isinstance(error, duckdb.BinderException):
            match = re.match(
                r'Binder Error: Referenced column "([^"\n]+)" '
                r"(?:not found in FROM clause!|was not found because "
                r"the FROM clause is missing)",
                text,
            )
            if match:
                return {
                    "exception_type": "Binder",
                    "error_subtype": "COLUMN_NOT_FOUND",
                    "name": match[1],
                }
        if isinstance(error, duckdb.CatalogException):
            match = re.match(
                r"Catalog Error: (Table|Scalar Function|Table Function|Type) "
                r"with name ([^\n]+) does not exist!",
                text,
            )
            if match:
                return {
                    "exception_type": "Catalog",
                    "error_subtype": "MISSING_ENTRY",
                    "type": match[1],
                    "name": match[2],
                }
        return {}
    try:
        value = json.loads(text[start:])
    except (ValueError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in cast(dict[str, object], value).items()
        if isinstance(item, str)
    }


def error_position(error: Exception) -> int | None:
    """Return DuckDB's zero-based UTF-8 byte offset when supplied."""

    value = error_details(error).get("position", "")
    return int(value) if value.isdecimal() else None


def _display_path(value: str) -> str:
    """Keep useful paths, stripping authentication-bearing URL components."""

    if "://" not in value:
        return value
    try:
        url = urlsplit(value)
        return urlunsplit((url.scheme, url.hostname or "", url.path, "", ""))
    except ValueError:
        return "[URL]"


def _diagnostic_reason(details: dict[str, str]) -> str | None:
    """Build messages from observed diagnostic forms, not wholesale text forwarding."""

    category = details.get("exception_type")
    message = details.get("exception_message", "")
    subtype = details.get("error_subtype")
    if category == "Binder" and subtype == "COLUMN_NOT_FOUND":
        # Candidate names can be generated from PIVOT row values. The missing
        # name is useful without echoing candidates whose provenance is unknown.
        return f"Column {details.get('name', '[unknown]')!r} was not found"
    if category == "Catalog" and subtype == "MISSING_ENTRY":
        object_type = details.get("type", "Object")
        name = details.get("name", "[unknown]")
        return f"{object_type} {name!r} was not found"
    if category == "Parser" and subtype == "SYNTAX_ERROR":
        return "SQL syntax is invalid" + (
            " at end of input" if message == "syntax error at end of input" else ""
        )
    if category in {"Conversion", "Invalid Input"}:
        match = re.match(r"Malformed JSON at byte (\d+) of input:", message)
        if match:
            return f"Malformed JSON at input byte {match[1]}"
    if category == "Conversion":
        if message.startswith("CSV Error on Line:"):
            line = re.search(r"^CSV Error on Line: (\d+)", message)
            column = re.search(r'Error when converting column "([^"\n]+)"', message)
            target = re.search(
                r"^Column .* is being converted as type ([A-Z0-9_ ()]+)$", message, re.M
            )
            path = re.search(r"^  file = (.+)$", message, re.M)
            parts = ["CSV conversion failed"]
            if path:
                parts.append(f"file {_display_path(path[1])!r}")
            if line:
                parts.append(f"input line {line[1]}")
            if column:
                parts.append(f"column {column[1]!r}")
            if target:
                parts.append(f"expected {target[1]}")
            return ", ".join(parts)
        target = re.search(
            r" to ([A-Z][A-Z0-9_]*(?:\([0-9, ]+\))?)"
            r"(?: when casting from source column [^\n]+)?$",
            message,
        )
        return f"A value could not be converted to {target[1]}" if target else None
    if category == "Constraint":
        match = re.fullmatch(
            r'Duplicate key "([^:]+): .*" violates (unique|primary key) constraint\.',
            message,
            re.S,
        )
        if match:
            # The first column is reliably separated from its value; remaining
            # composite-key columns cannot be recovered unambiguously from text.
            return f"Duplicate key violates {match[2]} constraint (column {match[1]!r})"
        match = re.match(
            r"CHECK constraint failed on table (\S+) with expression ", message
        )
        if match:
            return f"CHECK constraint failed on table {match[1]!r}"
    if category == "IO":
        match = re.fullmatch(r'No files found that match the pattern "(.*)"', message)
        if match:
            return f"No files match {_display_path(match[1])!r}"
    if category == "Permission":
        match = re.fullmatch(
            r'Cannot access file "(.*)" - file system operations '
            r"are disabled by configuration",
            message,
        )
        if match:
            return (
                f"File access is disabled by configuration: {_display_path(match[1])}"
            )
    return None
