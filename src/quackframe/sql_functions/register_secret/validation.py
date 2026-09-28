"""Compatibility imports for shared validation."""

from quackframe.credential_loading.validation import validate_azure_scope
from quackframe.sql_functions.validation import validate_identifier

__all__ = ["validate_azure_scope", "validate_identifier"]
