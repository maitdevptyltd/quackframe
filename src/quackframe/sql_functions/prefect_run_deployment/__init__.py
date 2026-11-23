"""Explicit SQL registration for the optional Prefect deployment capability."""

from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.prefect_run_deployment.function import (
    prefect_run_deployment,
)

prefect_run_deployment_function = SqlFunction(
    name="prefect_run_deployment",
    callable=prefect_run_deployment,
    side_effects=True,
    null_handling="special",
    required_modules=("prefect",),
)

__all__ = ["prefect_run_deployment_function"]
