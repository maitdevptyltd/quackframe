"""Readable SQL Agent outcomes, preserving the runtime's diagnostic policy."""

import json
from logging import Logger, StreamHandler

from quackframe.resources import SessionResources
from quackframe.sql_functions.mssql_run_job.models import JobResult


def report(result: JobResult, resources: SessionResources) -> str:
    """Report every recorded attempt and identify steps without history."""
    attempts = [
        {
            "history_id": row.id,
            "step_id": row.step_id,
            "step_name": row.step_name,
            "status": row.outcome.name.lower(),
            "started_at": row.started_at.isoformat(),
            "duration_seconds": row.duration_seconds,
            "error_number": row.error_number,
            "severity": row.severity,
            "message": row.message,
        }
        for row in result.history
    ]
    recorded = {row.step_id for row in result.history}
    missing = [
        {"step_id": step.id, "step_name": step.name, "status": "not_recorded"}
        for step in result.steps
        if step.id not in recorded
    ]
    payload = json.dumps(
        {
            "job_id": result.job.id,
            "job_name": result.job.name,
            "agent_session_id": result.job.session_id,
            "status": result.status,
            "attempts": attempts,
            "steps_without_history": missing,
        }
    )
    lines = [f"SQL Agent job {result.job.name} ({result.job.id}): {result.status}"]
    for row in result.history:
        label = (
            "Job summary" if row.step_id == 0 else f"Step {row.step_id} {row.step_name}"
        )
        lines.append(
            f"{label}: {row.outcome.name.lower()}, {row.duration_seconds}s, "
            f"history {row.id}, SQL {row.error_number}, "
            f"severity {row.severity}: {row.message}"
        )
    for step in result.steps:
        if step.id not in recorded:
            lines.append(
                f"Step {step.id} {step.name}: not recorded "
                "(skipped or history unavailable)"
            )
    if result.status == "unknown":
        lines.append(
            "Complete job/step history was not available; success cannot be confirmed."
        )
    rendered = "\n".join(lines)
    if resources.error_logger is not None:
        resources.error_logger.info(
            "%s", rendered, extra={"send_to_api": resources.include_error_details}
        )
    else:
        terminal = Logger("quackframe.mssql_run_job")
        terminal.addHandler(StreamHandler())
        terminal.info("%s", rendered)
    return payload
