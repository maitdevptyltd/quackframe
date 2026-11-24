"""Start one SQL Agent job and wait for its recorded terminal outcome."""

from math import isfinite
from time import monotonic, sleep
from uuid import UUID

from quackframe.errors import report_error_reason
from quackframe.resources import SessionResources
from quackframe.sql_functions.mssql_run_job.client import AgentClient
from quackframe.sql_functions.mssql_run_job.models import JobResult, Outcome
from quackframe.sql_functions.mssql_run_job.reporting import report


def mssql_run_job(
    resources: SessionResources,
    database: str,
    job_name: str | None = None,
    job_id: str | None = None,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
) -> str:
    """Return a JSON execution report only after the job and its steps succeed.

    Timeout or cancellation stops observation, not the remote SQL Agent job.
    There are no request retries or job resubmissions.
    """
    if (job_name is None) == (job_id is None):
        raise ValueError("Provide exactly one of job_name or job_id")
    if not database.strip():
        raise ValueError("database must name an attached MSSQL database")
    if job_name is not None and not job_name.strip():
        raise ValueError("job_name must not be empty")
    if job_id is not None:
        try:
            job_id = str(UUID(job_id))
        except ValueError:
            raise ValueError("job_id must be a valid UUID") from None
    poll_interval_seconds = (
        5.0 if poll_interval_seconds is None else poll_interval_seconds
    )
    for name, value in (
        ("timeout_seconds", timeout_seconds),
        ("poll_interval_seconds", poll_interval_seconds),
    ):
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be a finite positive number")

    resources.ensure_open()
    # The outer connection is executing this UDF. A duplicate uses the same
    # authenticated attachment while leaving ownership of the root unchanged.
    with resources.connection.duplicate() as connection:
        client = AgentClient(connection, database)
        client.validate_attachment()
        job = client.resolve(job_id, job_name)
        steps = client.steps(job)
        deadline = (
            monotonic() + timeout_seconds if timeout_seconds is not None else None
        )
        history = ()
        try:
            client.start(job)
            while True:
                client.check_session(job)
                history = client.history(job)
                terminal = next(
                    (
                        i
                        for i, row in enumerate(history)
                        if row.step_id == 0
                        and row.outcome
                        in (Outcome.SUCCEEDED, Outcome.FAILED, Outcome.CANCELLED)
                    ),
                    None,
                )
                if terminal is not None:
                    history = history[: terminal + 1]
                    break
                delay = poll_interval_seconds
                if deadline is not None:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            "Completion timeout; the remote job was not stopped"
                        )
                    delay = min(delay, remaining)
                sleep(delay)
        except Exception as error:
            report(JobResult(job, steps, history), resources)
            reason = report_error_reason(
                error,
                include_details=resources.include_error_details,
                error_logger=resources.error_logger,
            )
            # A lost response may follow an accepted submission. Never retry it.
            raise RuntimeError(
                f"SQL Agent job {job.id}: outcome unknown. {reason}. "
                "Check SQL Agent before retrying; the job may still be running."
            ) from None

        result = JobResult(job, steps, history)
        payload = report(result, resources)
        if not result.succeeded:
            raise RuntimeError(
                f"SQL Agent job {job.id} {result.status}; see the step report"
            )
        return payload
