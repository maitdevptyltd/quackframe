"""SQL-callable filesystem registration using shared credential loading."""

from duckdb import DuckDBPyConnection

from quackframe.credential_loading.loading import load_credentials
from quackframe.sql_functions.register_filesystem.models import get_filesystem_model


def register_filesystem(
    connection: DuckDBPyConnection,
    provider: str,
    reference: str,
    filesystem_type: str,
    overrides: dict[str, str] | None = None,
) -> bool:
    """Load a resolved strategy and register its standard filesystem protocols."""

    model_type = get_filesystem_model(filesystem_type)
    filesystem = load_credentials(provider, reference, model_type, overrides)

    # The duplicate shares the database instance with the executing connection.
    # DuckDB retains the registered backend after this short-lived handle closes.
    with connection.duplicate() as filesystem_connection:
        filesystem.register_filesystem_protocol(filesystem_connection)
    return True
