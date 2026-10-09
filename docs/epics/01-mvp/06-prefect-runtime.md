# Prefect Runtime

Status: **Complete**
Last updated: 2026-10-07
Epic: 01 MVP
Phase: 06
Related docs: [Runtime Adapters](../../runtime-adapters.md)

## Outcome

Provide optional Prefect flow and file-level task visibility while preserving
Quackframe's execution contract.

## Scope

- Add Prefect as an optional dependency.
- Wrap an invocation in one flow.
- Represent each SQL file as a filename-named task.
- Disable task caching for the shared live DuckDB connection.
- Reuse native Prefect profiles and environment settings.
- Keep Prefect imports inside the integration package.

## Validation

- Compare direct and Prefect-observed outcomes for the same files.
- Verify file tasks retain caller order and one shared session.
- Verify flow and task failure states identify the failed file safely.
- Prove base Quackframe remains importable without Prefect installed.

The [deployment entry-point phase](../06-prefect-deployment/01-deployment-entry-point.md)
extends this runtime with public `quackframe_flow`. It receives file paths and
prepares SQL inside the flow before opening DuckDB. File tasks consume the
prepared statements through the existing core engine. Runtime selection keeps
Prefect imports optional; the public integration can also be imported explicitly.

The flow name is fixed as `quackframe-run`. A downstream `[project].name` is
used as the flow-run name when available, while SQL-file task names use path
stems and retain full paths in Quackframe results and failures.

The adapter preserves every Quackframe error subclass and exception identity.
Regression tests cover configuration exit status, safe conversion failures at
the file-task boundary, and suppression of unexpected runtime diagnostics.
