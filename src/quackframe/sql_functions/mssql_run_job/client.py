"""Execute SQL Agent operations through an existing DuckDB MSSQL attachment."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from duckdb import DuckDBPyConnection

from quackframe.sql_functions.mssql_run_job.models import (
    History,
    Job,
    Outcome,
    Step,
)


class AgentClient:
    def __init__(self, connection: DuckDBPyConnection, database: str) -> None:
        self.connection = connection
        self.database = database

    def validate_attachment(self) -> None:
        rows = self.connection.execute(
            "SELECT type FROM duckdb_databases() WHERE database_name = ?",
            [self.database],
        ).fetchall()
        if not rows or rows[0][0] != "mssql":
            raise ValueError("database must name an attached MSSQL database")

    def query(self, sql: str, parameters: dict[str, object]) -> list[tuple[Any, ...]]:
        return self.connection.execute(
            "SELECT * FROM mssql_scan_params(?, ?, ?)",
            [self.database, sql, parameters],
        ).fetchall()

    def resolve(self, job_id: str | None, job_name: str | None) -> Job:
        selector = (
            "job_id = CONVERT(uniqueidentifier, @selector)"
            if job_id
            else ("name = @selector")
        )
        rows = self.query(
            "SELECT CONVERT(varchar(36), j.job_id), j.name, "
            "(SELECT MAX(session_id) FROM msdb.dbo.syssessions), "
            "COALESCE((SELECT MAX(instance_id) FROM msdb.dbo.sysjobhistory h "
            "WHERE h.job_id = j.job_id), 0) "
            f"FROM msdb.dbo.sysjobs j WHERE {selector}",
            {"selector": job_id or job_name},
        )
        if not rows:
            raise ValueError(
                "SQL Agent job was not found or is not visible to this login"
            )
        identifier, name, session_id, history_id = rows[0]
        if session_id is None:
            raise RuntimeError("SQL Agent has no recorded session")
        return Job(
            str(UUID(str(identifier))), str(name), int(session_id), int(history_id)
        )

    def steps(self, job: Job) -> tuple[Step, ...]:
        return tuple(
            Step(int(row[0]), str(row[1]), str(row[2]))
            for row in self.query(
                "SELECT step_id, step_name, subsystem FROM msdb.dbo.sysjobsteps "
                "WHERE job_id = CONVERT(uniqueidentifier, @requested_job_id) "
                "ORDER BY step_id",
                {"requested_job_id": job.id},
            )
        )

    def start(self, job: Job) -> None:
        # Check on the server immediately before submission. There is deliberately
        # no retry: a lost response may still mean Agent accepted this start.
        sql = (
            "DECLARE @id uniqueidentifier = "
            "CONVERT(uniqueidentifier, @requested_job_id); "
            "IF (SELECT MAX(session_id) FROM msdb.dbo.syssessions) <> @session_id "
            "THROW 50000, 'SQL Agent session changed before submission', 1; "
            "IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobactivity "
            "WHERE job_id = @id AND session_id = @session_id "
            "AND run_requested_date IS NOT NULL AND stop_execution_date IS NULL) "
            "THROW 50000, 'SQL Agent job is already queued or running', 1; "
            "IF COALESCE((SELECT MAX(instance_id) FROM msdb.dbo.sysjobhistory "
            "WHERE job_id = @id), 0) <> @history_id "
            "THROW 50000, 'Job history changed before submission; try again', 1; "
            "DECLARE @result int; "
            "EXEC @result = msdb.dbo.sp_start_job @job_id = @id; "
            "IF @result <> 0 THROW 50000, 'SQL Agent rejected the job start', 1;"
        )
        self.connection.execute(
            "SELECT mssql_exec_params(?, ?, ?)",
            [
                self.database,
                sql,
                {
                    "requested_job_id": job.id,
                    "session_id": job.session_id,
                    "history_id": job.history_id,
                },
            ],
        ).fetchall()

    def history(self, job: Job) -> tuple[History, ...]:
        rows = self.query(
            "SELECT instance_id, step_id, step_name, run_status, "
            "msdb.dbo.agent_datetime(run_date, run_time), "
            "(run_duration / 10000) * 3600 + ((run_duration % 10000) / 100) * 60 "
            "+ run_duration % 100, sql_message_id, sql_severity, message "
            "FROM msdb.dbo.sysjobhistory WHERE job_id = "
            "CONVERT(uniqueidentifier, @requested_job_id) "
            "AND instance_id > @history_id "
            "ORDER BY instance_id",
            {"requested_job_id": job.id, "history_id": job.history_id},
        )
        return tuple(
            History(
                int(row[0]),
                int(row[1]),
                str(row[2]),
                Outcome(row[3]),
                cast(datetime, row[4]),
                int(row[5]),
                int(row[6]),
                int(row[7]),
                str(row[8] or ""),
            )
            for row in rows
        )

    def check_session(self, job: Job) -> None:
        rows = self.query(
            "SELECT MAX(session_id) FROM msdb.dbo.syssessions "
            "WHERE session_id >= @session_id",
            {"session_id": job.session_id},
        )
        if not rows or rows[0][0] != job.session_id:
            raise RuntimeError("SQL Agent restarted; the job outcome is unknown")
