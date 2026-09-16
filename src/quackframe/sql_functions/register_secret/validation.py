"""Validate SQL-visible identifiers, secret types, and override maps."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from quackframe.sql_functions.register_secret.models import SecretType

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_TYPES = {"mssql", "azure_connection_string"}
_ALLOWED_OVERRIDES: dict[SecretType, frozenset[str]] = {
    "mssql": frozenset({"database", "port", "use_encrypt"}),
    "azure_connection_string": frozenset({"scope"}),
}


def parse_secret_type(value: str) -> SecretType:
    if value not in _SECRET_TYPES:
        raise ValueError(f"Unsupported secret type: {value}")
    return cast(SecretType, value)


def validate_identifier(value: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label.capitalize()} must be a simple SQL identifier")
    return value


def validate_overrides(
    secret_type: SecretType,
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    supplied = dict(overrides or {})
    unknown = sorted(set(supplied) - _ALLOWED_OVERRIDES[secret_type])
    if unknown:
        raise ValueError(
            f"Unsupported {secret_type} override field(s): {', '.join(unknown)}"
        )
    return supplied


def parse_boolean(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("use_encrypt override must be true or false")


def validate_azure_scope(value: str) -> str:
    if not value.startswith(("az://", "azure://", "abfss://")):
        raise ValueError("Azure scope must use an az://, azure://, or abfss:// URI")
    if not value.endswith("/"):
        raise ValueError("Azure scope must end with a trailing slash")
    if not value.split("://", maxsplit=1)[1].rstrip("/"):
        raise ValueError("Azure scope must identify a storage location")
    return value
