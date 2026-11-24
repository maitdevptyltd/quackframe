"""Register SQL Agent execution as an explicit, side-effecting SQL capability."""

from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.mssql_run_job.function import mssql_run_job

mssql_run_job_function = SqlFunction(
    name="mssql_run_job",
    callable=mssql_run_job,
    bind_resources=True,
    side_effects=True,
    null_handling="special",
)

__all__ = ["mssql_run_job_function"]
