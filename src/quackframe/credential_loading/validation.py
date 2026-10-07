"""Shared credential scope validation."""


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
