# Useful Error Diagnostics

Status: **Complete**
Last updated: 2026-10-16
Epic: 02 Result Logging
Phase: 02
Related docs: [Investigation](../../duckdb-error-investigation.md)

## Objective

Replace vague errors with actionable diagnostics while avoiding incidental
disclosure of data during ordinary SQL processing.

## 1. Preserve useful information

Report the error category, SQL filename, and accurate line/column where
available. Preserve ordinary diagnostic metadata such as missing table or
column names, expected types and relevant filenames.

Ordinary identifiers and paths are not treated as secrets merely because
someone could deliberately put a password in them.

## 2. Handle demonstrated data exposure

| Failure | Intended diagnostic |
| --- | --- |
| Conversion or malformed JSON | Explain the conversion problem and expected type without printing the rejected value. |
| Duplicate-key constraint | Identify the constraint or affected columns without printing the duplicate data. |
| CSV import | Preserve filename, input line/column and conversion details without reproducing the data row. |
| SQL syntax or binding | Preserve useful diagnostic details without copying unrelated data literals from SQL excerpts. |
| Credential-bearing URL | Preserve useful failure context without exposing authentication material. |
| PIVOT-derived suggestions | Avoid echoing suggestions containing automatically generated row values; retain the missing-column diagnosis and location. |

## 3. Use DuckDB's structured information

Use JSON diagnostic fields where they support these behaviours. Account for
the observed textual prefix, missing fields and UTF-8 byte positions. JSON
message text must not automatically be considered sanitised.

For unsupported diagnostic formats, retain the error category and available
location rather than guessing how to rewrite arbitrary text.

## 4. Correct failure locations

Map positions to the original SQL file, including multiline and Unicode input.
Correct statement attribution after PIVOT. Report only locations that can be
determined reliably.

## 5. Keep the implementation proportionate

Use focused handling for demonstrated ordinary failures. Do not build a
general-purpose secret detector or special protections for deliberately
password-named tables, paths used as function names, or explicit
error(password) calls.

Do not automatically forward arbitrary upstream exception text through the
safe diagnostic path. Ensure rendered exception chains do not reintroduce
values omitted from that diagnostic.

## Acceptance criteria

Targeted regression tests must demonstrate:

- Useful missing-column/table diagnostics.
- Accurate multiline, Unicode and post-PIVOT attribution.
- Useful conversion, constraint, JSON and CSV errors without rejected data.
- Authentication material omitted from the tested URL failure.
- Ordinary identifiers and filenames remain useful.
- Unsupported errors retain safe context.
- Omitted values do not reappear through rendered exception chains.

Reuse the investigation fixtures. Run only relevant tests and changed-file
checks.

## Outside this scope

Progress logging, result annotations and a redesign of the logging system.
Output routing is covered by the approved follow-up below.

## Related Docs

- [Investigation](../../duckdb-error-investigation.md): empirical evidence and practical assessment.
- [Execution lifecycle](../../execution-lifecycle.md): failure and execution semantics.
- [Runtime adapters](../../runtime-adapters.md): optional execution destinations.


## Implementation and validation

Implemented selected structured diagnostics and source-based statement attribution.
DuckDB tokenization identifies semicolon boundaries, including quoted strings and
comments; each original statement is executed whole so dynamic PIVOT internal
statements do not inflate counts. UTF-8 offsets map to original line/column.

No broad secret detector was added. Candidate suggestions
are omitted because their metadata does not distinguish generated row values.
Composite duplicate-key diagnostics retain the first identifiable column and
constraint type without attempting to parse subsequent values. Unknown formats
retain category/context and omit raw messages.

DuckDB's relation API returns text-only binder failures in some cases, ignoring
errors_as_json. Known missing-name diagnostics remain useful, but their missing
positions are reported as unknown rather than inferred or obtained by rerunning
SQL. Other supported execution/parser errors retain supplied positions.

Focused validation reuses recorded investigation outputs plus actual synthetic
execution regressions for row conversion, constraints, CSV, JSON, Unicode,
multiline source, PIVOT and rendered exception chains. The full repository suite
and the 84 investigation probes are not rerun.

Validation completed on 2026-10-15:

- `poetry run pytest tests/test_errors.py tests/test_execution.py -k 'not temporary_database and not result_logging_executes_every_row_exactly_once and not result_logging_detects_errors_beyond_preview' -q -p no:cacheprovider --basetemp=.test-tmp-diagnostics-final --tb=short`: **56 passed, 7 deselected**.
- Changed-file Ruff lint and format checks: passed.
- Pyright for `errors.py`, `sql.py` and `test_errors.py`: zero errors.
- Documentation link checker and `git diff --check`: passed.

Tests used the existing Poetry Python 3.13 environment with this worktree's `src`
on `PYTHONPATH`; no dependencies or live services were changed.

Review corrections preserve malformed-JSON byte details for both casts and JSON
functions (`Conversion` and `Invalid Input`). Structured diagnostics are requested
when opening the owned connection, before configuration locking takes effect;
execution no longer issues a per-file configuration mutation. Focused review
regressions cover `json(v)`, `json_extract(v, '$.key')`, and multiple files with
`lock_configuration=true`, including a useful error from the locked session.
The error suite passed **41 tests** after these corrections. Changed-file Ruff,
format and Pyright checks, documentation links and whitespace checks passed.

## Approved output routing

Terminal output reports full original error details for direct and Prefect
execution regardless of external permission. External logs and failure states
report the useful safe baseline by default; setting
`allow_external_error_logging=true` permits full original errors. The independent
`allow_external_result_logging` permission controls selected query results only.
Both permissions default to false and accept environment, explicit Python and
CLI overrides, but cannot be granted in project TOML. Users may enable selected
results while keeping errors sanitised, or enable full errors without permitting
results. Errors are reported in every case. Safe external failures must retain
suppressed original exception chains; original file/statement/line context remains available where supplied.

Routing validation: 79 focused diagnostic/routing/execution tests passed (7
unrelated or previously hazardous cases deselected); 11 affected CLI and mocked
Prefect regression cases passed (34 deselected). No Prefect service was started.
Changed-file lint/format and source/routing-test types passed. A wider touched-test
type check also found three pre-existing unknown-lambda typing diagnostics at
`tests/test_cli.py:240`; that unrelated test code was left unchanged.


## Independent permissions follow-up

The approved split is implemented in the typed model, environment loader,
explicit Python overrides and paired allow/deny CLI flags. Error routing in core
and both Prefect failure boundaries uses only `allow_external_error_logging`;
result selection and permission checks remain independent.

Validation on 2026-10-16: 56 focused tests passed (101 unrelated cases deselected),
covering both permissions independently, selected results with sanitised errors,
error permission without result permission, synthetic dotenv/environment/Python
precedence, TOML rejection and CLI overrides. Changed-file Ruff lint, source and
routing-test Pyright, documentation links and whitespace checks passed. The
broader config-test type check found ten pre-existing diagnostics in unchanged
lambda and DuckDB connection-configuration code; these remain out of scope.
Tests used the existing main-checkout Poetry environment with this worktree's
`src` on `PYTHONPATH`; no dependencies or live services were changed.

Independent review found no actionable correctness or readability issues. The
reviewer reran all 43 error-routing cases successfully and confirmed the final
whitespace check passed.


## Terminal and external destinations

Full backend diagnostics must reach the terminal for both direct and Prefect
execution. Prefect emits the full diagnostic through its run logger with
`extra={"send_to_api": config.allow_external_error_logging}`. Its console handler
receives that record in either mode; its API handler omits it when permission is
false. The exception raised into Prefect remains sanitised unless permission is
true, so task/flow failure records cannot disclose the original data indirectly.

Preparation before a Prefect run uses terminal logging directly. Core accepts an
optional error logger from the adapter for SQL execution, database setup and
function installation. No full diagnostics are stored on sanitised exceptions;
converted exceptions are raised after leaving the original exception handler.
Result permission and progress logging are unchanged.

Validate with installed Prefect API/console handlers and failed-state conversion,
using synthetic data and an intercepted outbound log sink without a live server.
Check both permission values, print capture, preparation, execution and setup.


Focused validation: 107 tests passed across destination routing, error
sanitisation, SQL-function installation and progress logging. Installed Prefect
handlers receive real records under a real task context with print capture;
only the outbound API-log sink is intercepted. Tests verify console detail in
both modes, permission-controlled outgoing records and failed-state messages,
serialised exception payloads, and absence of raw exception chains. Changed-file
Ruff and Pyright, documentation links and `git diff --check` pass. No live Prefect
service or customer data was used.

Independent review found no actionable correctness or readability issues and
reran 57 destination/routing/progress cases successfully. Six additional direct
CLI and mocked Prefect regressions passed (41 unrelated cases deselected).
Manual verification against the user's configured Prefect environment remains
for the user; [developer API](../../developer-api.md#check-error-destinations)
contains the synthetic SQL and the two acceptance commands.
