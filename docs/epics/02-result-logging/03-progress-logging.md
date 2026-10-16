# File And Statement Progress Logging

Status: **Complete**
Last updated: 2026-10-16
Epic: 02 Result Logging
Phase: 03
Related docs: [Execution Lifecycle](../../execution-lifecycle.md), [Runtime Adapters](../../runtime-adapters.md)

## Approved Scope

Core execution reports each SQL file and source statement starting,
completing, or failing. Completion and failure messages include elapsed
seconds measured with `perf_counter()`. Statements use one-based numbers within
their file. Progress includes the file path, never SQL text, returned values,
or exception details.

Direct execution writes progress to terminal stderr using standard Python
logging. The Prefect adapter passes its task run logger to the same core
function, retaining one task per file. CLI, F5, Python, and scheduled invocations
therefore share the same behaviour. No root logging configuration changes
or new settings are needed.

Progress is independent of result selection and the separate external result
and error permissions. Existing ordering, shared-session ownership, fail-fast
behaviour, cleanup, result rendering, and error conversion remain unchanged.
Preparation and setup failures happen before file execution starts and retain
their existing diagnostics; they do not claim a file or statement ran.

Result annotation and selection changes (R07) are outside this phase.

## Implementation And Validation

- Add lifecycle messages around the existing file/statement execution path.
- Route messages through a standard logger: a terminal handler for direct
  execution, or the supplied Prefect task logger for external execution.
- Test ordered success, failure and fail-fast behaviour, elapsed times, safe
  message content, selected-result interleaving, and mocked Prefect delivery.
- Run focused offline tests, lint, type checks, documentation links and diff
  checks before review. No live customer or Prefect API calls are required.

## Validation Results

- 71 focused progress, execution and error-routing tests passed.
- Five additional mocked Prefect task and CLI cases passed.
- Scoped Ruff, source/routing-test Pyright, Markdown links and diff checks passed.
  Including `tests/test_execution.py` in Pyright reports an existing DuckDB
  `create_function` overload typing diagnostic, outside the changed timing test.
- No full suite or live services were used. Downstream manual testing remains
  the user's next acceptance step.
- Independent review found no actionable R06 findings. Its progress/CLI run
  passed 20 cases and exposed one existing CLI cleanup-test mock signature
  mismatch (`include_error_details`), left outside this change. The reviewer
  suggested checking external failure progress content explicitly; that
  assertion was added and its four permission combinations passed.
