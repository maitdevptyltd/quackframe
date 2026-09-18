# SQL Result Logging

Status: **Planned**
Last updated: 2026-09-18
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

The setting is also available as `QUACKFRAME_LOG_SETTING`. An explicit
`--log-setting` CLI value or direct Python configuration value takes precedence
over the environment. Logging configuration is invocation and deployment
state; it is not accepted from checked-in project configuration.

External result delivery has a separate permission named
`allow_external_result_logging`, available through
`QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING`. It defaults to `false` and does not
change which statements the log setting selects. The CLI provides mutually
exclusive `--allow-external-result-logging` and
`--deny-external-result-logging` flags so an invocation can override either
environment value explicitly. Direct Python callers can provide the equivalent
Boolean configuration value. Checked-in project configuration cannot grant
this permission.

Selected results use DuckDB's native `DuckDBPyRelation` string representation.
DuckDB owns the table layout, displayed row and column limits, truncation
message, and value rendering. Quackframe does not fetch rows into a Python
collection or implement a second table renderer. Native rendering behaviour is
therefore tied to the pinned DuckDB version and may change only when that
dependency is deliberately upgraded.

## Runtime Behaviour

Core execution owns statement selection and exposes selected results through a
runtime-neutral reporting boundary. Selecting a runtime must not change which
statements qualify under the resolved log setting.

The direct runtime writes selected results to its terminal output. The Prefect
runtime uses Prefect's run logger from inside the corresponding decorated
SQL-file task, so the result is associated with that task's logs. Prefect
remains an optional integration and is not imported by Quackframe core.

Direct terminal output does not require external-result permission. A
non-direct runtime must fail before executing project SQL when the resolved log
setting would emit at least one result and external-result permission is
`false`. `all` therefore requires permission for every non-direct run;
`annotations-only` requires it when the prepared SQL contains at least one
valid result annotation; and `none` never requires it. Quackframe must not
silently downgrade or suppress an otherwise selected result.

When external-result permission is granted and the resolved selection can emit
results, the non-direct runtime emits one warning before project SQL executes
that returned values may be retained by the destination logging system.

Result logging does not change ordered execution, the shared DuckDB session,
fail-fast behaviour, task caching, retries, database cleanup, or SQL failure
semantics. An assertion statement such as `SELECT error(...)` continues to fail
the file, task, and run when its condition is true.

A selected statement is executed as a `DuckDBPyRelation` and that relation is
rendered exactly once. Quackframe must not execute the statement first and then
reconstruct or rerun it for display. Unselected statements continue through the
ordinary execution path without result rendering.

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
The separate external-result permission prevents an inherited environment log
setting from exposing values through a non-direct runtime without an explicit
deployment or invocation decision.

## Non-goals

- Providing an IDE result grid or selected-text execution.
- Exporting complete datasets or replacing file-oriented data export.
- Automatically deciding whether returned values are sensitive.
- Persisting result sets as Prefect results or artifacts.
- Changing project SQL assertions or verification logic.
- Building a general-purpose application logging framework.

## Open Decisions

- Which DuckDB statement result types count as result-producing beyond ordinary
  queries and `RETURNING` clauses.

## Implementation Boundaries

- Use DuckDB's parser and execution result metadata; do not implement a general
  SQL parser or split statements on semicolons.
- Associate an annotation with exactly the next DuckDB statement and reject or
  report misplaced annotations clearly.
- Obtain a `DuckDBPyRelation` for a selected result-producing statement and use
  its native string representation as the complete rendered payload.
- Render each selected relation exactly once. Do not execute a selected
  statement separately before rendering it, fetch its rows into a Python
  collection, or implement Quackframe-specific table formatting or truncation.
- Keep result selection and native relation rendering in core while adapters
  own delivery of the rendered string to their logging systems.
- Resolve direct Python and CLI values before environment values. Do not load
  either logging control from checked-in project configuration.
- Validate external-result permission before project SQL executes. A denied
  non-direct invocation that would emit results fails configuration rather than
  silently changing result selection.
- Obtain Prefect's run logger only within an active Prefect flow or task
  context.

## Validation

- Prove that omitted `--log-setting` resolves to `annotations-only`.
- Prove `--log-setting` overrides `QUACKFRAME_LOG_SETTING`.
- Prove `--allow-external-result-logging` and
  `--deny-external-result-logging` override both values of
  `QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING`.
- Prove `annotations-only`, `none`, and `all` across single- and multi-statement
  SQL files.
- Prove annotations bind to the intended DuckDB statement when SQL contains
  comments, quoted strings, and semicolons inside strings.
- Prove selected results are emitted once and unselected results remain silent.
- Prove selected results match DuckDB's native `DuckDBPyRelation` string
  representation, including DuckDB-owned truncation for larger results.
- Prove rendering does not execute a selected statement more than once,
  including statements with side effects or `RETURNING` clauses.
- Prove direct execution writes selected results to terminal output.
- Prove direct execution does not require external-result permission.
- Prove non-direct execution fails before project SQL when a result would be
  emitted without permission, while `none` and unannotated `annotations-only`
  runs remain allowed.
- Prove a permitted non-direct run emits one retention warning before project
  SQL and does not repeat it for each selected statement.
- Prove Prefect execution writes selected results through the corresponding
  file task's run logger without persisting task results.
- Prove base Quackframe execution still works without Prefect installed.
- Prove SQL errors still fail fast and close the shared session.
- Prove standard diagnostic paths do not emit full SQL text or credential
  values.
