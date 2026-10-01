"""Azure path translation and explicitly owned asynchronous Blob clients."""

from collections.abc import Callable
from contextlib import suppress
from glob import escape
from re import fullmatch, sub
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit
from weakref import finalize

from adlfs import AzureBlobFileSystem  # pyright: ignore[reportMissingTypeStubs]
from azure.identity.aio import ManagedIdentityCredential
from azure.storage.blob.aio import BlobServiceClient
from fsspec.asyn import get_loop  # pyright: ignore[reportMissingTypeStubs]
from fsspec.asyn import (  # pyright: ignore[reportMissingTypeStubs]
    sync as fsspec_sync,  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
)

from quackframe.sql_functions.register_filesystem.adapter import ProtocolFileSystem

# fsspec's synchronous bridge has no usable result annotation.
sync = cast(Callable[..., Any], fsspec_sync)


def connection_account(connection_string: str) -> str:
    """Accept explicit public-cloud connections without echoing secret input."""
    fields: dict[str, str] = {}
    try:
        for part in connection_string.rstrip(";").split(";"):
            key, value = part.split("=", 1)
            # The SDK preserves key whitespace. Reject it rather than validate
            # a different credential field from the one the SDK will receive.
            if key != key.strip():
                raise ValueError
            key = key.lower()
            if key in fields or not value:
                raise ValueError
            fields[key] = value
        account = fields["accountname"]
        allowed = {
            "accountname",
            "accountkey",
            "sharedaccesssignature",
            "defaultendpointsprotocol",
            "endpointsuffix",
            "blobendpoint",
        }
        if (
            not fullmatch(r"[a-z0-9]{3,24}", account)
            or fields.keys() - allowed
            or fields.get("defaultendpointsprotocol", "https") != "https"
            or fields.get("endpointsuffix", "core.windows.net") != "core.windows.net"
            or ("accountkey" in fields) == ("sharedaccesssignature" in fields)
            or fields.get(
                "blobendpoint", f"https://{account}.blob.core.windows.net"
            ).rstrip("/")
            != f"https://{account}.blob.core.windows.net"
        ):
            raise ValueError
    except (ValueError, KeyError):
        raise ValueError(
            "Azure filesystem requires a public-cloud HTTPS connection string "
            "with an account name and either an account key or SAS"
        ) from None
    return account


def validate_scope(account: str, scope: str | None) -> None:
    """Validate Azure location syntax without imposing a directory root."""
    try:
        if not fullmatch(r"[a-z0-9]{3,24}", account) or scope is None:
            raise ValueError
        url = urlsplit(scope)
        if (
            not scope.endswith("/")
            or url.query
            or url.fragment
            or url.port is not None
            or url.password is not None
            or any(character.isspace() for character in url.netloc)
        ):
            raise ValueError
        if url.scheme in {"az", "azure"} and url.username is None:
            container = url.netloc
        elif (
            url.scheme == "abfss" and url.hostname == f"{account}.dfs.core.windows.net"
        ):
            container = url.username or ""
        else:
            raise ValueError
        _validate_container(container)
    except ValueError:
        raise ValueError(
            "Azure filesystem scope must identify a container with a trailing "
            "slash and match its configured account"
        ) from None


def _validate_container(container: str) -> None:
    if not (
        fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", container)
        and "--" not in container
    ) and container not in {"$root", "$web"}:
        raise ValueError("Azure filesystem URL must identify a valid container")


class OwnedBlobServiceClient(BlobServiceClient):
    """Close the client and its identity once, including backend finalization."""

    owned_identity: ManagedIdentityCredential | None = None
    closed: bool = False

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await super().close()
        finally:
            if self.owned_identity is not None:
                await self.owned_identity.close()


class ExplicitAzureFileSystem(AzureBlobFileSystem):
    """Keep adlfs operations while bypassing ambient connection selection."""

    def __init__(
        self, client: OwnedBlobServiceClient, account: str, **kwargs: Any
    ) -> None:
        self._owned_client = client
        # The marker prevents adlfs creating an implicit credential. do_connect
        # attaches our existing client instead of parsing this connection value.
        try:
            super().__init__(  # pyright: ignore[reportUnknownMemberType]
                account_name=account,
                connection_string="quackframe-owned-client",
                anon=False,
                skip_instance_cache=True,
            )
        finally:
            # adlfs 2026.8 retains self in its finalizer arguments and does not
            # expose the handle. Our session owner already guarantees cleanup,
            # including failed construction. Detach only this instance's hooks
            # so the global finalizer registry cannot retain closed backends.
            registry = cast("dict[finalize[..., Any], object]", finalize._registry)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            for finalizer in list(registry):
                details = finalizer.peek()
                if details is not None and details[0] is self:
                    finalizer.detach()

    def do_connect(self) -> None:
        self.connection_string = None
        self.account_key = None
        self.sas_token = None
        self.client_id = None
        self.client_secret = None
        self.tenant_id = None
        self.credential = None
        self.sync_credential = None
        self.service_client = self._owned_client

    @classmethod
    def _strip_protocol(cls, path: str) -> str:
        # The outer adapter already validated and decoded the URL. Running
        # adlfs URL parsing again would discard literal # and ?versionid= names.
        return path.lstrip("/")

    def split_path(
        self,
        path: str,
        delimiter: str = "/",
        return_container: bool = False,
        **kwargs: Any,
    ) -> tuple[str, str, None]:
        container, _, blob = self._strip_protocol(path).partition(delimiter)
        return container, blob, None

    def _open(self, path: str, mode: str = "rb", *args: Any, **kwargs: Any) -> Any:
        if mode != "rb":
            raise ValueError("Azure filesystem registrations support reads only")
        return SafeAzureReader(
            super()._open(path, mode, *args, **kwargs)  # pyright: ignore[reportUnknownMemberType]
        )


class SafeAzureReader:
    """Sanitize deferred SDK errors after fsspec has returned an open file."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._reader, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            try:
                return attribute(*args, **kwargs)
            except Exception:
                raise OSError("Azure filesystem file operation failed") from None

        return invoke

    def __enter__(self) -> "SafeAzureReader":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def create_azure_filesystem(
    protocol: str,
    account: str,
    scope: str | None,
    *,
    connection_string: str | None = None,
    client_id: str | None = None,
) -> ProtocolFileSystem:
    """Construct isolated clients and transfer their lifetime to one adapter."""
    validate_scope(account, scope)
    loop = get_loop()
    identity: ManagedIdentityCredential | None = None
    client: OwnedBlobServiceClient | None = None

    async def construct() -> OwnedBlobServiceClient:
        nonlocal identity
        if connection_string is not None:
            return OwnedBlobServiceClient.from_connection_string(connection_string)
        # Azure Identity otherwise also selects federated workload credentials
        # from the environment, which is a different authentication contract.
        identity = ManagedIdentityCredential(
            client_id=client_id, _exclude_workload_identity_credential=True
        )
        result = OwnedBlobServiceClient(
            f"https://{account}.blob.core.windows.net", credential=identity
        )
        result.owned_identity = identity
        return result

    def close() -> None:
        if client is not None:
            sync(loop, client.close)
        elif identity is not None:
            sync(loop, identity.close)

    try:
        client = cast(OwnedBlobServiceClient, sync(loop, construct))
        backend = ExplicitAzureFileSystem(client, account, skip_instance_cache=True)
        to_backend, from_backend, to_glob = azure_paths(protocol, account)
        return ProtocolFileSystem(
            backend,
            protocol,
            to_backend,
            from_backend,
            close,
            to_glob=to_glob,
            skip_instance_cache=True,
        )
    except BaseException as error:
        with suppress(Exception):
            close()
        if not isinstance(error, Exception):
            raise
        raise RuntimeError(
            "Azure filesystem could not be created; check credentials and dependencies"
        ) from None


def azure_paths(
    protocol: str,
    account: str,
) -> tuple[Callable[[str], str], Callable[[str], str], Callable[[str], str]]:
    """Translate explicit account URLs and preserve reusable discovery results."""

    def to_backend(path: str, *, glob_pattern: bool = False) -> str:
        try:
            url = urlsplit(path)
            if (
                url.scheme != protocol
                or url.netloc != account
                or url.query
                or url.fragment
                or not url.path.startswith("/")
            ):
                raise ValueError
        except ValueError:
            raise ValueError(
                "Azure filesystem URL must match its registered account"
            ) from None
        value = url.path[1:]
        _validate_container(unquote(value.split("/", 1)[0]))
        if glob_pattern:
            value = sub(
                r"%(?:2[aA]|3[fF]|5[bBdD])",
                lambda match: escape(chr(int(match.group()[1:], 16))),
                value,
            )
        return unquote(value)

    def from_backend(path: str) -> str:
        return f"{protocol}://{account}/{quote(path, safe='/')}"

    return to_backend, from_backend, lambda path: to_backend(path, glob_pattern=True)
