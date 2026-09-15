# Ordered SQL Execution

Status: **Planned**
Last updated: 2026-09-15
Epic: 01 MVP
Phase: 02
Related docs: [Execution Lifecycle](../../execution-lifecycle.md)

## Outcome

Execute caller-supplied SQL files predictably in one DuckDB session.

## Scope

- Validate a non-empty ordered SQL-file list.
- Open and close one configured DuckDB session.
- Use DuckDB statement extraction.
- Execute files serially and stop on first failure.
- Return typed results and raise safe typed failures.
- Apply the approved database lifecycle after connection closure.

## Validation

- Test single-file and ordered multi-file execution.
- Prove temporary tables and other session state cross file boundaries.
- Test empty, missing, invalid, and failing SQL files.
- Verify later files do not run after failure.
- Verify diagnostics exclude full SQL and arbitrary returned data by default.
