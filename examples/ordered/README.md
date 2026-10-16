# Ordered Files Example

This example demonstrates the shared-session invariant. The first file creates
a temporary table, and the second file queries it.

Run both files in explicit order:

```powershell
quackframe run `
    sql/01-prepare.sql `
    sql/02-report.sql
```

Running `02-report.sql` by itself should fail because F5 and single-file CLI
execution do not infer prerequisites.

The checked-in configuration uses an empty function allowlist because this
example demonstrates shared DuckDB session state without Python extensions.
