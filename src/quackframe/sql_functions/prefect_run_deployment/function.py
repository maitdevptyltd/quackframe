"""Start one Prefect deployment and require its successful completion."""

from typing import NoReturn, cast
from uuid import UUID, uuid4

from quackframe.errors import OptionalDependencyError


def prefect_run_deployment(
    deployment_id: str | None = None,
    deployment_entrypoint: str | None = None,
) -> str:
    """Launch once, wait for completion, and return the successful run's UUID.

    Queued and running deployments are awaited without a completion deadline.
    Native Prefect request timeouts still govern individual API operations.
    """

    # None defaults let SQL callers name their options. NULL must still fail
    # validation instead of making DuckDB skip this side-effecting function.
    if (deployment_id is None) == (deployment_entrypoint is None):
        raise ValueError(
            "Provide exactly one of deployment_id or deployment_entrypoint"
        )

    identifier: UUID | str
    if deployment_id is not None:
        try:
            identifier = UUID(deployment_id)
        except (ValueError, AttributeError):
            raise ValueError("deployment_id must be a valid deployment UUID") from None
        description = f"Prefect deployment {identifier}"
    else:
        assert deployment_entrypoint is not None
        parts = deployment_entrypoint.split("/")
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(
                "deployment_entrypoint must have the form 'flow/deployment'"
            )
        identifier = deployment_entrypoint
        # Caller-supplied names are not safe diagnostic text. Use the resolved
        # deployment UUID later, once Prefect returns a run.
        description = "Prefect deployment selected by entrypoint"

    try:
        from prefect.client.schemas.objects import FlowRun
        from prefect.deployments import run_deployment
        from prefect.settings import PREFECT_API_URL
    except ImportError:
        raise OptionalDependencyError(
            "Deployment execution requires 'quackframe[prefect]'"
        ) from None

    # A missing URL must not start an ephemeral server that cannot own this ID.
    if not PREFECT_API_URL.value():
        raise ValueError("Configure PREFECT_API_URL before running a deployment")

    try:
        # Force a synchronous result even when SQL is called from an async flow.
        # A key protects the create request against Prefect's HTTP retries; each
        # separate SQL invocation intentionally receives a new key.
        flow_run = cast(
            FlowRun,
            run_deployment(
                name=identifier,
                timeout=None,
                idempotency_key=str(uuid4()),
                as_subflow=True,
                _sync=True,  # pyright: ignore[reportCallIssue]
            ),
        )
    except Exception:
        _fail(
            f"{description}: could not establish the run outcome. "
            "Check the server before retrying; a run may already have been created."
        )

    state = flow_run.state
    if state is not None and state.is_completed():
        return str(flow_run.id)

    if flow_run.deployment_id is not None:
        description = f"Prefect deployment {flow_run.deployment_id}"
    context = f"{description}, run {flow_run.id}"
    if state is not None and state.is_final():
        _fail(
            f"{context}: finished in state {state.type.value}. "
            "Check the run in Prefect."
        )
    _fail(
        f"{context}: Prefect did not return a final outcome; check the run in Prefect."
    )


def _fail(message: str) -> NoReturn:
    """Keep known-safe run context visible when SQL errors are redacted externally."""

    from prefect import get_run_logger
    from prefect.exceptions import MissingContextError

    try:
        logger = get_run_logger()
    except MissingContextError:
        pass
    else:
        # Do not include state messages or raw API errors: they can contain data.
        logger.error("%s", message)
    raise RuntimeError(message) from None
