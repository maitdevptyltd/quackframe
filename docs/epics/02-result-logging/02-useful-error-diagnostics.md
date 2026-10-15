# Useful Error Diagnostics

Status: **Complete**
Last updated: 2026-10-15
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

External-output permissions, full-error routing, progress logging, result
annotations and a redesign of the logging system.

## Related Docs

- [Investigation](../../duckdb-error-investigation.md): empirical evidence and practical assessment.
- [Execution lifecycle](../../execution-lifecycle.md): failure and execution semantics.
- [Runtime adapters](../../runtime-adapters.md): optional execution destinations.


## Implementation and validation

Implemented selected structured diagnostics and source-based statement attribution.
DuckDB tokenization identifies semicolon boundaries, including quoted strings and
comments; each original statement is executed whole so dynamic PIVOT internal
statements do not inflate counts. UTF-8 offsets map to original line/column.

No broad secret detector or new output setting was added. Candidate suggestions
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
