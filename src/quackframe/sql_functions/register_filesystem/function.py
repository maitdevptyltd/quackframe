"""SQL-callable registration of independently owned filesystem protocols."""

from contextlib import suppress
from re import fullmatch

from quackframe.credential_loading.loading import load_credentials
from quackframe.errors import OptionalDependencyError
from quackframe.resources import SessionResources
from quackframe.sql_functions.register_filesystem.models import get_filesystem_model

# Native handlers need reserving even when absent from list_filesystems().
_NATIVE_PROTOCOLS = frozenset(
    {
        "file",
        "http",
        "https",
        "s3",
        "s3a",
        "s3n",
        "gs",
        "gcs",
        "r2",
        "az",
        "azure",
        "abfs",
        "abfss",
        "hf",
        "hdfs",
        "sftp",
        "ssh",
        "sshfs",
        "duckdb",
        "md",
        "memory",
    }
)


def register_filesystem(
    resources: SessionResources,
    provider: str,
    reference: str,
    filesystem_type: str,
    protocol: str | None = None,
    overrides: dict[str, str] | None = None,
) -> bool:
    """Reserve a protocol, resolve credentials once, and retain explicit cleanup."""

    selected = reference if protocol is None else protocol
    if (
        not isinstance(selected, str)  # pyright: ignore[reportUnnecessaryIsInstance]
        or fullmatch(r"[a-z][a-z0-9+.-]*", selected) is None
    ):
        raise ValueError("Filesystem protocol must match [a-z][a-z0-9+.-]*")
    model_type = get_filesystem_model(filesystem_type)
    try:
        from fsspec import (  # pyright: ignore[reportMissingTypeStubs]
            available_protocols,
        )
    except ImportError:
        raise OptionalDependencyError(
            "Filesystem registration requires "
            f"'quackframe[{model_type.extra_dependency_bundle}]'"
        ) from None
    if selected in _NATIVE_PROTOCOLS or selected in available_protocols():
        raise ValueError("Filesystem protocol is reserved by an existing backend")

    # The owner lock protects reservation and publication, never file reads.
    # DuckDB also arbitrates conflicts from other owners sharing this instance.
    with resources.lock:
        resources.ensure_open()
        registration = resources.connection.duplicate()
        try:
            if registration.filesystem_is_registered(selected):
                raise ValueError("Filesystem protocol is already registered")
            # DuckDB exposes only the first scheme of an external Python FS.
            # Refuse unknown wrappers rather than risk an invisible secondary
            # scheme capturing reads intended for this registration.
            if any(
                not resources.owns(f"filesystem:{name}")
                for name in registration.list_filesystems()
            ):
                raise ValueError(
                    "External Python filesystem protocols cannot be verified; "
                    "use one shared SessionResources owner for registrations"
                )
            model = load_credentials(provider, reference, model_type, overrides)
            filesystem = model.create_filesystem(selected)
        except BaseException:
            registration.close()
            raise

        try:
            registration.register_filesystem(filesystem)
        except BaseException as error:
            with suppress(Exception):
                filesystem.close_backend()
            registration.close()
            if not isinstance(error, Exception):
                raise
            raise RuntimeError("Filesystem could not be registered") from None

        def cleanup() -> None:
            # Keep a handle until unregistration, then release backend resources
            # even if DuckDB rejects removal or a transport close fails.
            try:
                registration.unregister_filesystem(selected)
            finally:
                try:
                    filesystem.close_backend()
                finally:
                    registration.close()

        resources.add_cleanup(cleanup, name=f"filesystem:{selected}")
    return True
