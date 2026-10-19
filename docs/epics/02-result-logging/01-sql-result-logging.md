# SQL Result Logging

Status: **In Progress**
Last updated: 2026-10-16
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

R07 approved placement: an annotation on its own line immediately before SQL
selects the following statement. A `-- quackframe: log-result` comment on the
same line after a statement selects that preceding statement, including after
its semicolon or on the final statement without a semicolon. It must never
select the next statement. Existing result-type support and external permissions
are unchanged; CALL, EXPLAIN and MERGE support belongs to R08. Implementation
and focused annotation regression validation are complete, with independent
review clearance. The phase remains in progress for its other criteria.

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
therefore depends on the installed DuckDB version and may vary across allowed
patch releases (`>=1.5.5,<1.6`).

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

A selected statement is fully materialized once into a temporary DuckDB table
through its `DuckDBPyRelation`. Native rendering reads a bounded preview of that
table without re-executing the original relation. The temporary table and source
view are removed afterward. Unselected statements continue through the ordinary
execution path without result rendering.

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

## Supported Statements

R08 adds `CALL`, `EXPLAIN` (including `EXPLAIN ANALYZE`), and `MERGE ... RETURNING`
to the existing query and INSERT/UPDATE/DELETE RETURNING forms. Both annotations
and `all` select these results. MERGE without RETURNING remains unselected.
The existing materialization and native rendering path must execute each selected
statement once to completion, including side effects, before emitting its preview.
Offline tests cover all three logging modes, complete execution beyond the preview,
failure propagation, and the existing independent external logging permissions.

## Implementation Boundaries

- Use DuckDB's parser and execution result metadata; do not implement a general
  SQL parser or split statements on semicolons.
- Associate an annotation with its intended DuckDB statement according to
  standalone or trailing placement and reject or
  report misplaced annotations clearly.
- Materialize a selected relation once in a uniquely named temporary DuckDB
  table, then use that table's native relation rendering as the complete payload.
- Do not re-execute the original relation to render it, fetch its rows into a
  Python collection, or implement Quackframe-specific formatting or truncation.
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

R08 implementation is complete on 2026-10-16. The existing DuckDB materialization
path handles the newly selected forms without changes. The 82-case execution run
passed, followed by the final 23-case additional-statement suite including plain
EXPLAIN. Tests prove 30,000 sequence evaluations occur exactly once, INSERT and
MERGE side effects complete, native previews stay bounded, late failures stop the
file, and external result permission remains independent of error permission.
Scoped Ruff, formatting, Pyright (zero errors), documentation links and whitespace
checks pass. Test/type checks required running outside the sandbox because its
temporary-directory and environment access failed. No live services were used.
The phase remains In Progress for its other criteria.

The 2026-10-13 R02 fix is verified against DuckDB 1.5.5 with offline synthetic
data. All 12 selected tests passed (11 deselected): late failure and exactly-once
counting-UDF regressions in all three modes, native truncation, both RETURNING
paths, and existing output-selection cases. Exact targeted command:

```powershell
poetry run pytest tests/test_execution.py -k 'result_logging_detects_errors_beyond_preview or result_logging_executes_every_row_exactly_once or native_relation_rendering_owns_truncation or returning_after_unicode_emits_and_executes_once or annotations_only_emits_only_annotated_results or none_ignores_annotations or all_emits_annotated_and_unannotated_results_once' -p no:cacheprovider --tb=short
```

Changed-file checks: `poetry run ruff check src/quackframe/sql.py tests/test_execution.py`,
`poetry run ruff format --check src/quackframe/sql.py tests/test_execution.py`, and
`git diff --check` pass. Initial sandbox attempts failed on temporary-directory
permissions; the same targeted selection passed outside the sandbox. No broad
tests, type checks, dependency changes, live-system checks, or separate review
cycle were run. The phase remains in progress because R02 does not reassess
the remaining phase criteria. Full results occupy DuckDB temporary storage until
rendering finishes; only the rendered preview crosses into Python.

The 2026-10-02 terminal-formatting fix is implemented: Prefect result messages
begin with a newline, keeping the native table below the log prefix. The focused
adapter regression checks one log call with the complete native rendering.
Validation: 19 focused adapter and execution tests, source/test Ruff checks,
Pyright, documentation links, and whitespace checks pass. Repository-wide Ruff
still reports existing prototype issues under `MAD.Utilities.DuckDB`.
The phase remains in progress; this fix does not reassess all phase criteria.

The 2026-10-16 annotation placement fix keeps same-line comments in the preceding
source statement and checks annotations against the original SQL, including
trailing comments omitted by DuckDB's parsed statement. Validation: 43 focused
annotation and RETURNING tests plus eight final-statement cases passed, as did
scoped Ruff, documentation links,
and whitespace checks. Scoped Pyright reports one existing unknown
`create_function` overload in the unchanged execution test; the SQL module
passes scoped Pyright. Independent review found that an adjacent block comment
could be consumed as part of an unquoted token, allowing its annotation text to
select a result. The token match now stops before block comments, with regression
coverage for single-line and multiline comments. A second finding showed that
an intervening block comment could leave a same-line annotation attached to the
next statement. Statement splitting and annotation detection now share a small
comment reader that skips whole block comments and recognises the trailing line
annotation. Regressions cover ordinary and nested block comments. Independent
re-review cleared both findings with 45 focused annotation/RETURNING tests
passing and a clean whitespace check. R08 remains outside this change.

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
