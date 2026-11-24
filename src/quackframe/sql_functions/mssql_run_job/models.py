"""SQL Agent execution records used by the runner and its report."""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Outcome(IntEnum):
    FAILED = 0
    SUCCEEDED = 1
    RETRY = 2
    CANCELLED = 3
    RUNNING = 4


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    session_id: int
    history_id: int


@dataclass(frozen=True)
class Step:
    id: int
    name: str
    subsystem: str


@dataclass(frozen=True)
class History:
    id: int
    step_id: int
    step_name: str
    outcome: Outcome
    started_at: datetime
    duration_seconds: int
    error_number: int
    severity: int
    message: str


@dataclass(frozen=True)
class JobResult:
    job: Job
    steps: tuple[Step, ...]
    history: tuple[History, ...]

    @property
    def summary(self) -> History | None:
        return next(
            (
                row
                for row in self.history
                if row.step_id == 0
                and row.outcome
                in (Outcome.SUCCEEDED, Outcome.FAILED, Outcome.CANCELLED)
            ),
            None,
        )

    @property
    def succeeded(self) -> bool:
        # Agent can report overall success after following a failed step's
        # continuation rule. Require each executed step's final attempt to pass.
        final_attempts = {row.step_id: row for row in self.history if row.step_id}
        return (
            self.summary is not None
            and self.summary.outcome == Outcome.SUCCEEDED
            and (not self.steps or bool(final_attempts))
            and all(row.outcome == Outcome.SUCCEEDED for row in final_attempts.values())
        )

    @property
    def status(self) -> str:
        if self.summary is None:
            return "unknown"
        if self.summary.outcome in (Outcome.FAILED, Outcome.CANCELLED):
            return "failed"
        if self.steps and not any(row.step_id for row in self.history):
            return "unknown"
        return "succeeded" if self.succeeded else "failed"
