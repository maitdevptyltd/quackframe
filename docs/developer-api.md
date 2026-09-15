# Developer API

Status: proposed public contract for the MVP.

Quackframe has three developer entry points. Each resolves the same
configuration and delegates to the same execution engine.

## Command Line

Run one SQL file:

```powershell
quackframe run sql/example.sql
```

Run several files in one shared DuckDB session:

```powershell
quackframe run `
    sql/01-prepare.sql `
    sql/02-transform.sql `
    sql/03-validate.sql
```

Files execute in the supplied order and execution stops on the first failure.
The CLI returns a scheduler-friendly process exit code and identifies the
failed file and statement without logging full SQL or returned query data by
default.

Proposed one-run overrides include:

```powershell
quackframe run --runtime direct sql/example.sql
quackframe run --runtime prefect sql/example.sql
quackframe run --memory sql/example.sql
quackframe run --database-path ./scratch.duckdb sql/example.sql
quackframe run --config ./alternate.toml sql/example.sql
```

The exact database flags remain subject to the database-lifecycle decision in
[Configuration](configuration.md#open-decisions).

## Visual Studio Code F5

F5 is a first-class developer experience implemented as a thin wrapper over the
CLI:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Quackframe: Run current SQL",
      "type": "node-terminal",
      "request": "launch",
      "command": "quackframe run \"${file}\"",
      "cwd": "${workspaceFolder}"
    }
  ]
}
```

F5 runs only the active SQL file. It does not discover neighbouring files or
infer prerequisites. A file that depends on earlier setup must be invoked in an
explicit ordered command or through a future approved job-definition contract.

The `node-terminal` launch type must be validated against supported VS Code
installations. A task-backed equivalent may become the documented fallback.

## Python API

The common embedded call should mirror the CLI:

```python
from quackframe import run

result = run(
    [
        "sql/01-prepare.sql",
        "sql/02-transform.sql",
    ]
)
```

Direct configuration values are explicit overrides:

```python
from quackframe import QuackframeConfig, run

config = QuackframeConfig(runtime="direct")
result = run(["sql/example.sql"], config=config)
```

An `ExecutionPlan` may be introduced for callers that construct or validate
runs programmatically, but ordinary use should not require it.

On success, `run()` returns a typed `ExecutionResult`. On failure, it raises a
typed `ExecutionError` containing safe execution context such as the file and
statement number. Runtime-specific identifiers may appear as generic metadata;
core result types must not expose Prefect or another adapter's classes.

## SQL Function API

Quackframe functions use a schema-qualified public name:

```sql
SELECT quackframe.register_secret(
    'prefect',
    'reporting-reader',
    'mssql',
    'reporting_reader'
);
```

The public macro delegates to a private connection-scoped Python UDF such as
`_quackframe_register_secret`. Downstream callers never need to quote a dotted
function name or call the private implementation.

Each function owns its implementation and support code as a self-contained
unit. It conforms only to the minimal registration, naming, safety, and
diagnostic contract needed to coexist in Quackframe.

## Entry-point Invariants

- Every entry point uses the same configuration model.
- Every invocation has one selected runtime adapter.
- Every invocation owns one DuckDB session.
- File order is explicit and stable.
- Runtime adapters preserve core behaviour.
- Optional integrations do not become core imports.
- Scheduled execution uses the CLI rather than a separate API.

## Related Docs

- [Developer Examples](developer-examples.md): concise usage paths.
- [Execution Lifecycle](execution-lifecycle.md): behaviour shared by all entry
  points.
- [Configuration](configuration.md): defaults and overrides.
- [Runtime Adapters](runtime-adapters.md): direct and Prefect execution.
- [SQL Function Extensions](python-extensions.md): function packaging and
  registration.
