"""Self-contained SQL function for temporary DuckDB secret registration."""

from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.register_secret.function import register_secret

register_secret_function = SqlFunction(
    name="register_secret",
    callable=register_secret,
    bind_connection=True,
    side_effects=True,
    null_handling="special",
)

__all__ = ["register_secret_function"]
