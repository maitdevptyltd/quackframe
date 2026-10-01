"""Expose one configured backend through an independently named URI scheme."""

from collections.abc import Callable
from typing import Any, cast

from fsspec import AbstractFileSystem  # pyright: ignore[reportMissingTypeStubs]


class ProtocolFileSystem(AbstractFileSystem):
    """Translate both input paths and discovery results without changing clients."""

    def __init__(
        self,
        backend: Any,
        protocol: str,
        to_backend: Callable[[str], str],
        from_backend: Callable[[str], str],
        close_backend: Callable[[], None],
        to_glob: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)  # pyright: ignore[reportUnknownMemberType]
        self.backend = backend
        self.protocol = protocol  # pyright: ignore[reportAttributeAccessIssue]
        self.to_backend = to_backend
        self.from_backend = from_backend
        self.close_backend = close_backend
        self.to_glob = to_glob or to_backend

    @classmethod
    def _strip_protocol(cls, path: str) -> str:
        # Keep the authority until the strategy validates it. fsspec's default
        # stripping would discard the information needed to reject wrong hosts.
        return path

    def _open(
        self,
        path: str,
        mode: str = "rb",
        block_size: int | None = None,
        autocommit: bool = True,
        cache_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        target = self.to_backend(path)
        try:
            return self.backend.open(
                target,
                mode=mode,
                block_size=block_size,
                autocommit=autocommit,
                cache_options=cache_options,
                **kwargs,
            )
        except Exception:
            raise OSError(
                "Registered filesystem could not open the requested file"
            ) from None

    def info(self, path: str, **kwargs: Any) -> dict[str, Any]:
        target = self.to_backend(path)
        try:
            result = dict(self.backend.info(target, **kwargs))
        except Exception:
            raise OSError(
                "Registered filesystem could not inspect the requested file"
            ) from None
        result["name"] = self.from_backend(result["name"])
        return result

    def ls(self, path: str, detail: bool = True, **kwargs: Any) -> Any:
        target = self.to_backend(path)
        try:
            entries = self.backend.ls(target, detail=detail, **kwargs)
        except Exception:
            raise OSError(
                "Registered filesystem could not list the requested path"
            ) from None
        if detail:
            return [
                dict(entry, name=self.from_backend(entry["name"])) for entry in entries
            ]
        return [self.from_backend(entry) for entry in entries]

    def glob(self, path: str, maxdepth: int | None = None, **kwargs: Any) -> Any:
        target = self.to_glob(path)
        try:
            entries = self.backend.glob(target, maxdepth=maxdepth, **kwargs)
        except Exception:
            raise OSError(
                "Registered filesystem could not discover the requested files"
            ) from None
        if isinstance(entries, dict):
            return {
                self.from_backend(name): dict(entry, name=self.from_backend(name))
                for name, entry in cast(dict[str, dict[str, Any]], entries).items()
            }
        return [self.from_backend(entry) for entry in entries]

    def modified(self, path: str) -> Any:
        details = self.info(path)
        if "mtime" in details:
            return details["mtime"]
        # Backends such as Azure expose their timestamp through modified()
        # rather than the SFTP metadata key.
        try:
            return self.backend.modified(self.to_backend(path))
        except Exception:
            raise OSError(
                "Registered filesystem could not inspect the requested timestamp"
            ) from None
