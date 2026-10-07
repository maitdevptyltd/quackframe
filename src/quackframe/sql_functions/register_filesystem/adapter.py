"""Expose one configured backend through an independently named URI scheme."""

from collections.abc import Callable
from contextlib import suppress
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
            return SafeFile(
                self.backend.open(
                    target,
                    mode=mode,
                    block_size=block_size,
                    autocommit=autocommit,
                    cache_options=cache_options,
                    **kwargs,
                )
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
        # DuckDB joins listing names to the directory itself during recursive
        # overwrite. Glob results remain complete, reusable protocol URLs.
        if detail:
            return [
                dict(entry, name=self.from_backend(entry["name"]).rsplit("/", 1)[-1])
                for entry in entries
            ]
        return [self.from_backend(entry).rsplit("/", 1)[-1] for entry in entries]

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

    def mkdir(self, path: str, create_parents: bool = True, **kwargs: Any) -> None:
        target = self.to_backend(path)
        try:
            self.backend.mkdir(target, create_parents=create_parents, **kwargs)
        except Exception:
            raise OSError(
                "Registered filesystem could not create the directory"
            ) from None

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        target = self.to_backend(path)
        try:
            self.backend.makedirs(target, exist_ok=exist_ok)
        except Exception:
            raise OSError(
                "Registered filesystem could not create the directory"
            ) from None

    def rm(
        self, path: str, recursive: bool = False, maxdepth: int | None = None
    ) -> None:
        target = self.to_backend(path)

        def remove_exact(location: str, depth: int = 0) -> None:
            # fsspec's generic rm expands globs. Output URLs name exact files
            # and directories, even when their decoded names contain * or ?.
            if recursive and self.backend.info(location)["type"] == "directory":
                if maxdepth is not None and depth >= maxdepth:
                    raise ValueError("Removal exceeded its maximum directory depth")
                for entry in self.backend.ls(location, detail=True):
                    remove_exact(entry["name"], depth + 1)
                self.backend.rmdir(location)
            else:
                self.backend.rm_file(location)

        try:
            remove_exact(target)
        except Exception:
            raise OSError("Registered filesystem could not remove the path") from None

    def mv(
        self,
        path1: str,
        path2: str,
        recursive: bool = False,
        maxdepth: int | None = None,
        **kwargs: Any,
    ) -> None:
        source, target = self.to_backend(path1), self.to_backend(path2)
        try:
            if recursive:
                kwargs["recursive"] = True
            if maxdepth is not None:
                kwargs["maxdepth"] = maxdepth
            self.backend.mv(source, target, **kwargs)
        except Exception:
            raise OSError("Registered filesystem could not move the path") from None


class SafeFile:
    """Keep deferred reads, writes and upload finalization errors free of secrets."""

    def __init__(self, file: Any) -> None:
        self._file = file

    def write(self, data: bytes) -> int:
        try:
            written = self._file.write(data)
        except Exception:
            raise OSError("Registered filesystem file operation failed") from None
        # Paramiko acknowledges the complete write but returns None. DuckDB
        # requires the standard binary-file byte count for its export writer.
        return len(data) if written is None else int(written)

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._file, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            try:
                return attribute(*args, **kwargs)
            except Exception:
                raise OSError("Registered filesystem file operation failed") from None

        return invoke

    def __enter__(self) -> "SafeFile":
        return self

    def __exit__(self, *args: Any) -> None:
        if args[0] is None:
            self.close()
        else:
            # Retain the operation's primary failure if cleanup also fails.
            with suppress(Exception):
                self.close()
