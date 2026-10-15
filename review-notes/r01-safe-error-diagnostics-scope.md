# R01: Useful errors without sensitive data

Status: **Draft scope — implementation not started**
Last updated: 2026-10-15
Source: [Maitland's R01 comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323234)

## Objective

Replace vague error summaries with useful diagnostics that identify what went
wrong and where, without exposing customer row values or credentials.

This is task one of R01. Task two, error-output permissions and destination
rules, is separate.

## What Maitland suggested

- Include the error type and the location in the SQL file.
- Parser, binder and catalog errors could probably provide more detail because
  they describe SQL and object names rather than row data. His example is a
  misspelled column, with the correct candidate column names and a line marker.
- Investigate DuckDB's `SET errors_as_json = true`, which he suggests can expose
  error type and character position separately from the message.
- Correct inaccurate statement attribution, including failures after `PIVOT`.

His suggestion that these error categories are safe is tentative. This scope
does not assume every message in those categories is safe to publish verbatim.

## Proposed implementation scope

1. **Preserve useful safe details.** For supported parser, binder and catalog
   failures, report the specific problem and relevant non-sensitive identifiers
   where they can be safely extracted. Do not forward entire messages solely
   because their exception type is on an allowlist: messages can contain SQL
   excerpts, literals, paths or other sensitive text.
2. **Report accurate locations.** Include the SQL file and original file line,
   and column where available. Correct statement attribution after `PIVOT`.
   If DuckDB provides no reliable position, retain the available file/statement
   context rather than inventing an exact line.
3. **Use structured diagnostics where practical.** Investigate JSON errors
   with synthetic inputs before choosing the implementation. Verify which
   fields DuckDB actually supplies and how positions map to the original file.
   Structured output is not automatically safe output.
4. **Keep unsafe details out.** Conversion failures must omit offending cell
   values. Credential-bearing URLs, connection strings and arbitrary exception
   text must not escape through messages or exception chains. Unclassified
   errors should retain a safe error category and available location rather
   than collapsing everything to "The operation failed". Do not automatically
   expose arbitrary `SELECT error(...)` messages or provider error text.

Illustrative safe output:

```text
example.sql, line 4: Column "order_idd" was not found.
Available columns: "order_id", "order_date".

example.sql, line 12: A value could not be converted to INTEGER.
```

The exact wording and available fields depend on the verified diagnostic data.

## Acceptance and targeted tests

- A misspelled column identifies the column and correct file line.
- A syntax error late in a multiline file identifies its original file line.
- A failure after `PIVOT` is attributed correctly.
- Synthetic sensitive values in conversion errors, SQL literals and
  credential-bearing errors are absent from safe output and rendered exception
  chains, including parser/binder/catalog cases used to justify richer output.
- Unsupported diagnostic shapes retain safe context without leaking raw text.
- Run only focused diagnostic/location tests and relevant changed-file checks;
  no full suite or live services.

## Excluded from this task

No new settings, changes to `allow_external_result_logging`, full-error output
routes, or local-versus-external permission decisions. No R06 progress logging
or R07 result-selection/annotation changes. R01 remains open until its separate
output-control task is also addressed.

## Related Docs

- [Review checklist](maitland-pr-2.md#r01-useful-sql-errors): overall R01 status.
- [Execution lifecycle](../docs/execution-lifecycle.md): failure semantics.
- [Runtime adapters](../docs/runtime-adapters.md): execution destinations.
