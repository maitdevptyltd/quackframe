"""SQL function for explicit standard filesystem registration."""

from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.register_filesystem.function import register_filesystem

register_filesystem_function = SqlFunction(
    name="register_filesystem",
    callable=register_filesystem,
    bind_connection=True,
    side_effects=True,
    null_handling="special",
)

__all__ = ["register_filesystem_function"]
