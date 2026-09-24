"""Shared identifier and scope validation for ``register_secret``."""

from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str, label: str) -> str:
    """Allow only names that are safe to place directly into generated SQL."""

    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label.capitalize()} must be a simple SQL identifier")
    return value


def validate_azure_scope(value: str) -> str:
    """Require a supported, non-empty Azure URI ending in a slash."""

    supported_prefixes = ("az://", "azure://", "abfss://")
    if not value.startswith(supported_prefixes):
        expected_prefixes = "az://, azure://, or abfss://"
        raise ValueError(f"Azure scope must use an {expected_prefixes} URI")
    if not value.endswith("/"):
        raise ValueError("Azure scope must end with a trailing slash")
    if not value.split("://", maxsplit=1)[1].rstrip("/"):
        raise ValueError("Azure scope must identify a storage location")
    return value
