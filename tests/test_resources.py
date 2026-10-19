"""Session resource ownership independent of any filesystem backend."""

from unittest.mock import Mock

import duckdb
import pytest

from quackframe.errors import QuackframeError
from quackframe.resources import SessionResources
from quackframe.sql_functions import registry
from quackframe.sql_functions.definition import SqlFunction
from quackframe.sql_functions.installer import install_functions


def test_resource_cleanup_attempts_all_and_preserves_primary_error() -> None:
    cleanup = Mock(side_effect=RuntimeError("protected-value"))
    other = Mock()
    with (
        pytest.raises(ValueError, match="primary") as captured,
        SessionResources(Mock()) as resources,
    ):
        resources.add_cleanup(other)
        resources.add_cleanup(cleanup)
        raise ValueError("primary")
    other.assert_called_once()
    assert captured.value.__notes__ == ["Session resource cleanup also failed"]
    with (
        pytest.raises(QuackframeError, match="Session resource cleanup failed"),
        SessionResources(Mock()) as resources,
    ):
        resources.add_cleanup(cleanup)


def test_resource_binding_requires_owner_before_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup = Mock()

    def acquire(resources: SessionResources, value: str) -> str:
        resources.add_cleanup(cleanup)
        return value

    definition = SqlFunction(
        name="acquire", callable=acquire, bind_resources=True, side_effects=True
    )
    monkeypatch.setattr(registry, "BUILTIN_FUNCTIONS", (definition,))
    with duckdb.connect() as connection:
        with pytest.raises(RuntimeError, match="SessionResources"):
            install_functions(connection, ("acquire",))
        assert connection.execute(
            "SELECT count(*) FROM information_schema.schemata "
            "WHERE schema_name='quackframe'"
        ).fetchone() == (0,)
        with SessionResources(connection) as resources:
            install_functions(connection, ("acquire",), resources)
            assert connection.execute(
                "SELECT quackframe.acquire('value')"
            ).fetchone() == ("value",)
            cleanup.assert_not_called()
        cleanup.assert_called_once()


def test_binding_modes_are_mutually_exclusive() -> None:
    def bound(owner: SessionResources) -> bool:
        return True

    definition = SqlFunction(
        name="invalid",
        callable=bound,
        bind_connection=True,
        bind_resources=True,
    )
    with pytest.raises(RuntimeError, match="one function binding mode"):
        definition.validate()
