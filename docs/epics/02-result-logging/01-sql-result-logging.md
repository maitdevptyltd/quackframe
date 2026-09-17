# SQL Result Logging

Status: **Planned**
Last updated: 2026-09-17
Epic: 02 Result Logging
Phase: 01
Related docs: [Developer API](../../developer-api.md), [Execution Lifecycle](../../execution-lifecycle.md), [Runtime Adapters](../../runtime-adapters.md)

## Outcome

SQL authors can deliberately emit useful query results from Quackframe runs.
The same selection rules apply to direct and adapter-backed execution: direct
runs write selected results to the terminal, while the Prefect runtime writes
them to the corresponding SQL-file task log.

## Accepted Scope

Quackframe exposes one invocation setting named `--log-setting` with three
values:

- `annotations-only` logs only explicitly annotated statement results. This is
  the default when the caller does not supply `--log-setting`.
- `none` logs no statement results and ignores result annotations.
- `all` logs every result-producing statement.

SQL authors select an individual statement with a comment immediately before
that statement:

```sql
-- quackframe: log-result
SELECT
    verification_status,
    mismatch_count
FROM verification_summary;
```

Each selected result is emitted once. An annotation does not duplicate output
when `all` is selected.

## Runtime Behaviour

Core execution owns statement selection and exposes selected results through a
runtime-neutral reporting boundary. Selecting a runtime must not change which
statements qualify under the resolved log setting.

The direct runtime writes selected results to its terminal output. The Prefect
runtime uses Prefect's run logger from inside the corresponding decorated
SQL-file task, so the result is associated with that task's logs. Prefect
remains an optional integration and is not imported by Quackframe core.

Result logging does not change ordered execution, the shared DuckDB session,
fail-fast behaviour, task caching, retries, database cleanup, or SQL failure
semantics. An assertion statement such as `SELECT error(...)` continues to fail
the file, task, and run when its condition is true.

## Data Handling Boundary

Result logging deliberately emits returned values. Those values may be
sensitive, and an adapter or logging platform may retain them according to its
own configuration. The annotation makes the SQL author's intent reviewable;
it does not classify or redact the returned data.

Quackframe must not add returned rows to `SqlFileResult`, `ExecutionResult`,
Prefect task results, or persisted Quackframe metadata. Unselected results are
not emitted. Existing protections against logging credentials, bound secret
values, and full SQL text remain in force.

`none` provides an invocation-level way to suppress all result logging. `all`
is an explicit decision to emit every result-producing statement in the run.

## Non-goals

- Providing an IDE result grid or selected-text execution.
- Exporting complete datasets or replacing file-oriented data export.
- Automatically deciding whether returned values are sensitive.
- Persisting result sets as Prefect results or artifacts.
- Changing project SQL assertions or verification logic.
- Building a general-purpose application logging framework.

## Open Decisions

- The maximum number of rows and columns emitted for one statement.
- How truncation is indicated when a result exceeds that limit.
- The terminal and Prefect table-rendering format, including treatment of
  multiline or unusually wide values.
- Whether `log_setting` is only an invocation option or is also accepted from
  project configuration, environment configuration, and the Python API.
- Whether non-direct runtimes receive a warning before any result values can be
  retained, and the exact warning text.
- Which DuckDB statement result types count as result-producing beyond ordinary
  queries and `RETURNING` clauses.

## Implementation Boundaries

- Use DuckDB's parser and execution result metadata; do not implement a general
  SQL parser or split statements on semicolons.
- Associate an annotation with exactly the next DuckDB statement and reject or
  report misplaced annotations clearly.
- Fetch rows only for statements selected by the resolved log setting.
- Keep result selection and bounded capture in core while adapters own delivery
  to their logging systems.
- Obtain Prefect's run logger only within an active Prefect flow or task
  context.

## Validation

- Prove that omitted `--log-setting` resolves to `annotations-only`.
- Prove `annotations-only`, `none`, and `all` across single- and multi-statement
  SQL files.
- Prove annotations bind to the intended DuckDB statement when SQL contains
  comments, quoted strings, and semicolons inside strings.
- Prove selected results are emitted once and unselected results remain silent.
- Prove direct execution writes selected results to terminal output.
- Prove Prefect execution writes selected results through the corresponding
  file task's run logger without persisting task results.
- Prove base Quackframe execution still works without Prefect installed.
- Prove SQL errors still fail fast and close the shared session.
- Prove standard diagnostic paths do not emit full SQL text or credential
  values.

