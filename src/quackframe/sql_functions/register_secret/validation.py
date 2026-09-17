"""Validate SQL identifiers used by ``register_secret``."""

from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str, label: str) -> str:
    """Allow only names that are safe to place directly into generated SQL."""

    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label.capitalize()} must be a simple SQL identifier")
    return value
