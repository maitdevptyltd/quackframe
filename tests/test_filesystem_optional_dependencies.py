"""The generic SQL functions stay usable without filesystem dependencies."""

import subprocess
import sys

import duckdb
import pytest

from quackframe.sql_functions.register_filesystem.function import register_filesystem


def test_function_installation_does_not_import_optional_backends() -> None:
    script = """
import sys
from importlib.abc import MetaPathFinder
class BlockOptional(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'prefect', 'fsspec', 'paramiko'}:
            raise ModuleNotFoundError(name=fullname)
sys.meta_path.insert(0, BlockOptional())
import duckdb
from quackframe.sql_functions.installer import install_functions
with duckdb.connect() as connection:
    install_functions(connection, ('register_secret', 'register_filesystem'))
    try:
        connection.execute(
            "SELECT quackframe.register_filesystem('prefect', 'source', 'sftp')"
        )
    except duckdb.InvalidInputException as error:
        assert 'quackframe[sftp]' in str(error)
    else:
        raise AssertionError('Missing dependencies must fail when selected')
assert not {'prefect', 'fsspec', 'paramiko'}.intersection(sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_unknown_filesystem_is_rejected_before_provider_loading() -> None:
    with (
        duckdb.connect() as connection,
        pytest.raises(ValueError, match="Unsupported filesystem type"),
    ):
        register_filesystem(connection, "unused", "unused", "azure")
