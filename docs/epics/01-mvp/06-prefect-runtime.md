# Prefect Runtime

Status: **Planned**
Last updated: 2026-09-15
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
