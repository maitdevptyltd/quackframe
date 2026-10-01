"""Shared model resolution and optional integration boundaries."""

import subprocess
import sys
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from quackframe.credential_loading import loading
from quackframe.credential_loading.models import CredentialModel
from quackframe.sql_functions.register_secret.models import (
    AzureConnectionStringSecret,
    AzureManagedIdentitySecret,
    MssqlSecret,
    SshPrivateKeySecret,
)


@pytest.mark.parametrize(
    ("original", "overrides", "field", "expected"),
    [
        (
            MssqlSecret(
                host="sql.example.test",
                user=SecretStr("reader"),
                password=SecretStr("protected"),
                database="Original",
            ),
            {"database": "Reporting", "port": "1444", "use_encrypt": "NO"},
            "database",
            "Reporting",
        ),
        (
            AzureConnectionStringSecret(
                connection_string=SecretStr("protected"), scope="az://original/"
            ),
            {"scope": "az://reports/"},
            "scope",
            "az://reports/",
        ),
        (
            AzureManagedIdentitySecret(account_name="storage", scope="az://original/"),
            {"scope": "az://reports/"},
            "scope",
            "az://reports/",
        ),
        (
            SshPrivateKeySecret(
                username=SecretStr("reader"),
                key_path="/key",
                scope="sftp://original.example.test/",
            ),
            {"scope": "sftp://reports.example.test/"},
            "scope",
            "sftp://reports.example.test/",
        ),
    ],
)
def test_loading_preserves_strategy_and_saved_values(
    monkeypatch: pytest.MonkeyPatch,
    original: CredentialModel,
    overrides: dict[str, str],
    field: str,
    expected: str,
) -> None:
    before = original.model_dump()
    provider = Mock()
    provider.resolve.return_value = original
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))

    result = loading.load_credentials("example", "reference", type(original), overrides)

    provider.resolve.assert_called_once_with("reference", type(original))
    assert type(result) is type(original)
    assert getattr(result, field) == expected
    assert original.model_dump() == before


@pytest.mark.parametrize("missing", ["all", "fsspec", "paramiko"])
def test_optional_dependencies_are_loaded_only_when_selected(missing: str) -> None:
    # A fresh process proves import isolation even when the parent test suite
    # has already imported Prefect and fsspec for integration tests.
    script = r"""
import importlib.abc
import sys
from unittest.mock import patch

missing = sys.argv[1]
blocked = (
    {"prefect", "fsspec", "paramiko", "adlfs", "azure"}
    if missing == "all" else {missing}
)

class MissingIntegrations(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in blocked:
            raise ModuleNotFoundError("protected import detail", name=fullname)
        return None

sys.meta_path.insert(0, MissingIntegrations())

import duckdb
from pydantic import SecretStr
from quackframe.credential_loading.providers import registry
from quackframe.errors import OptionalDependencyError
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem.models import SftpFilesystem
from quackframe.sql_functions.register_secret.models import MssqlSecret

class LocalProvider:
    def resolve(self, reference, model_type):
        return model_type(host="example", user=SecretStr("reader"),
                          password=SecretStr("protected"), database="Reporting")

registry.PROVIDER_REGISTRY += (registry.ProviderRegistration(
    name="local", module_name="__main__", implementation_name="LocalProvider",
    missing_dependency="example", missing_dependency_message="Install example",
),)

with duckdb.connect() as connection, SessionResources(connection) as resources:
    install_functions(connection, ("register_secret", "register_filesystem"), resources)
    with patch.object(MssqlSecret, "register_duckdb_secret") as register:
        assert connection.execute(
            "SELECT quackframe.register_secret('local', 'login', 'mssql')"
        ).fetchone() == (True,)
        register.assert_called_once()

    strategy = SftpFilesystem(username=SecretStr("reader"), key_path="/key",
                              scope="sftp://example.test/")
    try:
        strategy.create_filesystem("example-files")
    except OptionalDependencyError as error:
        assert "quackframe[sftp]" in str(error)
        assert "protected" not in str(error)
    else:
        raise AssertionError("Missing backend should fail")

if missing == "all":
    try:
        registry.get_provider("prefect")
    except OptionalDependencyError as error:
        assert "quackframe[prefect]" in str(error)
    else:
        raise AssertionError("Missing provider should fail")

assert not (blocked & sys.modules.keys())
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, missing],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("missing", ["fsspec", "paramiko", "fsspec,paramiko"])
def test_core_tests_collect_and_run_without_backend_dependencies(
    missing: str,
) -> None:
    script = r"""
import importlib.abc
import sys

blocked = set(sys.argv[1].split(','))
class MissingBackend(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] in blocked:
            raise ModuleNotFoundError(
                "Backend intentionally unavailable", name=fullname
            )
        return None
sys.meta_path.insert(0, MissingBackend())

try:
    import fsspec
except ModuleNotFoundError:
    fsspec_available = False
else:
    fsspec_available = True

import pytest
class Outcomes:
    passed = set()
    skipped = set()
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' and report.passed:
            self.passed.add(report.nodeid)
        if report.skipped:
            self.skipped.add(report.nodeid)
outcomes = Outcomes()
arguments = ['tests/test_register_filesystem.py', 'tests/test_resources.py',
    '-q', '-p', 'no:cacheprovider',
    '-k', 'not ordered_files']
assert pytest.main(arguments, plugins=[outcomes]) == 0
assert any('unknown_type' in node for node in outcomes.passed)
assert any('resource_cleanup_attempts' in node for node in outcomes.passed)
assert any('sftp_constructor' in node for node in outcomes.skipped)
if fsspec_available:
    assert any('sql_forms' in node for node in outcomes.passed)
else:
    assert any('sql_forms' in node for node in outcomes.skipped)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, missing],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("missing", ["fsspec", "adlfs", "azure"])
def test_azure_optional_dependencies_have_actionable_errors(missing: str) -> None:
    script = r"""
import importlib.abc
import sys
from unittest.mock import patch

class MissingAzure(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] == sys.argv[1]:
            raise ModuleNotFoundError('protected', name=fullname)
        return None
sys.meta_path.insert(0, MissingAzure())

import duckdb
from quackframe.errors import OptionalDependencyError
from quackframe.resources import SessionResources
from quackframe.sql_functions.installer import install_functions
from quackframe.sql_functions.register_filesystem.function import register_filesystem
from quackframe.sql_functions.register_filesystem.models import (
    AzureManagedIdentityFilesystem,
)

model = AzureManagedIdentityFilesystem(account_name='examplestorage', scope='az://reports/')
with duckdb.connect() as connection, SessionResources(connection) as resources:
    install_functions(connection, ('register_filesystem',), resources)
    with patch(
        'quackframe.sql_functions.register_filesystem.function.load_credentials',
        return_value=model,
    ):
        try:
            register_filesystem(
                resources, 'example', 'reports-files', 'azure_managed_identity'
            )
        except OptionalDependencyError as error:
            assert 'quackframe[azure]' in str(error)
            assert 'protected' not in str(error)
        else:
            raise AssertionError('Missing Azure dependency should fail')
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, missing],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
