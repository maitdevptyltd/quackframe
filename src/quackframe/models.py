"""Results shared by direct execution and optional runtimes."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class SqlFileResult:
    """Report the safe outcome of one executed SQL file.

    Results retain path, statement count, and elapsed time without retaining
    SQL text or returned query data.
    """

    path: Path
    statement_count: int
    elapsed: timedelta


@dataclass(frozen=True)
class ExecutionResult:
    """Report one successful run without runtime-specific types.

    The command line, direct Python calls, and optional runtimes all return this
    same result shape.
    """

    runtime: str
    database_mode: str
    files: tuple[SqlFileResult, ...]
    elapsed: timedelta

    @property
    def statement_count(self) -> int:
        """Return the completed statement count across every executed file."""

        return sum(file.statement_count for file in self.files)
