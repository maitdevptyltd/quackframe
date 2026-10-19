"""Explicit lifetime for resources acquired by connection-aware extensions."""

from collections.abc import Callable
from threading import RLock
from types import TracebackType
from typing import Self

from duckdb import DuckDBPyConnection

from quackframe.errors import QuackframeError


class SessionResources:
    """Keep extension resources alive until their caller finishes all SQL work."""

    def __init__(self, connection: DuckDBPyConnection) -> None:
        self.connection = connection
        self.lock = RLock()
        self._callbacks: list[Callable[[], None]] = []
        self._names: set[str] = set()
        self._closed = False

    def __enter__(self) -> Self:
        self.ensure_open()
        return self

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Session resources are already closed")

    def owns(self, name: str) -> bool:
        """Identify resources registered through this shared owner."""
        with self.lock:
            return name in self._names

    def add_cleanup(
        self, callback: Callable[[], None], name: str | None = None
    ) -> None:
        with self.lock:
            self.ensure_open()
            if name is not None:
                if name in self._names:
                    raise ValueError("Session resource is already registered")
                self._names.add(name)
            self._callbacks.append(callback)

    def close(self) -> None:
        with self.lock:
            if self._closed:
                return
            self._closed = True
            failed = False
            for callback in reversed(self._callbacks):
                try:
                    callback()
                except Exception:
                    failed = True
            self._callbacks.clear()
            self._names.clear()
            if failed:
                raise QuackframeError("Session resource cleanup failed") from None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.close()
        except Exception:
            if exc is None:
                raise
            exc.add_note("Session resource cleanup also failed")
