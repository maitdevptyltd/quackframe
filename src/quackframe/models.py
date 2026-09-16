"""Core execution contracts shared by every runtime adapter."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class SqlFileResult:
    """Non-sensitive outcome for one executed SQL file."""

    path: Path
    statement_count: int
    elapsed: timedelta


@dataclass(frozen=True)
class ExecutionResult:
    """Framework-independent outcome for one successful invocation."""

    runtime: str
    database_mode: str
    files: tuple[SqlFileResult, ...]
    elapsed: timedelta

    @property
    def statement_count(self) -> int:
        """Return the total number of completed statements."""
        return sum(file.statement_count for file in self.files)
