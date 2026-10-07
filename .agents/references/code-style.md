# Quackframe Code Style

Use this reference for implementation work once the package exists.

## Python

- Follow the supported Python versions declared in project metadata.
- Prefer strongly typed public contracts so editor autocomplete and type
  feedback are useful. Use precise types for execution plans, runtime adapters,
  observers, extension registries, credential providers, results, and
  configuration.
- Public contracts and interfaces should have explicit return types. Internal
  helpers may omit return annotations when inference is clear and stable.
- Keep Prefect and other orchestrator dependencies out of core code. Optional
  integrations may import their respective frameworks.
- Keep credential-provider implementations out of core execution. Core may
  define provider-facing contracts without depending on a concrete store.
- Use Pydantic for configuration and boundary models when structured validation
  materially improves the contract.
- Keep functions small and single-purpose, but avoid premature abstraction.
- Prefer explicit exceptions with actionable, non-sensitive messages over broad
  catch-and-log behaviour.

## Design Philosophy

- Treat code as liability. Prefer the smallest implementation that clearly
  satisfies the contract.
- Add abstraction when it reduces real complexity, protects a public contract,
  or makes a proven extension boundary maintainable.
- Use established patterns such as adapter, strategy, protocol, registry, and
  observer where they clarify replaceable integrations.
- Do not use patterns as decoration. Prefer a plain function or small dataclass
  when it is easier to understand and change.
- Keep extension points explicit around runtime adapters, SQL-callable Python
  functions, credential providers, event observation, and configuration.
- Keep each non-trivial SQL function in its own function-named package. Do not
  make independent functions share theme-level abstractions merely because
  their use cases sound related.
- Prefer local duplication to restrictive coupling. Extract shared behaviour
  only when its invariant and reason to change are genuinely shared.
- Keep execution semantics in core. Adapters translate lifecycle and events to
  an external system without silently redefining order, retries, caching,
  concurrency, cleanup, or failure behaviour.

## Code Like Prose

- Group related ideas with whitespace the way prose uses paragraphs.
- Prefer clear names over comments. Name functions by outcome, booleans
  positively, and values with units or data-shape cues where useful.
- Add docstrings for multi-step helpers that orchestrate a flow. Describe the
  path and contract rather than narrating syntax.
- Use paragraph-style comments before non-obvious blocks to explain why the
  step exists or which invariant it protects.
- Avoid comments that merely restate the code.
- Comment at boundaries such as session ownership, adapter translation,
  extension registration, cleanup policy, redaction, and failure conversion.
- Prefer guard clauses and named helpers over deeply nested control flow.

For adapter-backed execution, this is the target shape:

```python
def run_execution_plan(
    plan: ExecutionPlan,
    observer: ExecutionObserver,
) -> ExecutionResult:
    """Run the validated plan in one DuckDB session and report its lifecycle."""

    validated_plan = validate_execution_plan(plan)
    observer.execution_started(validated_plan)

    with open_duckdb_session(validated_plan.database) as session:
        for sql_file in validated_plan.sql_files:
            execute_sql_file(session, sql_file, observer)

    return observer.execution_succeeded(validated_plan)
```

## DuckDB And SQL

- Treat SQL files as trusted, reviewable operational code owned by consuming
  repositories.
- Preserve caller-supplied file order and one shared DuckDB session when the
  execution plan requires it.
- Use DuckDB parameter binding for values. Do not interpolate untrusted values
  into generated SQL.
- Centralise and test generated identifiers, quoting, and SQL-callable function
  registration.
- Keep the function registrar and SQL runner independent of concrete function
  names and function-specific request models.
- Bind connection-aware callables before DuckDB registration and omit the bound
  connection from the SQL-visible signature.
- Keep the built-in function registry explicit. Do not discover built-ins by
  scanning modules or directories.
- Keep job-specific attachments, transformations, copies, and validation in
  SQL unless an accepted Quackframe contract establishes otherwise.
- Do not log full SQL, returned query data, or credential values by default.

## Tests

- Add focused unit tests for new behaviour, edge cases, and failure paths.
- Test core execution without Prefect or another optional integration installed.
- Use temporary `.duckdb` files for disk-backed lifecycle and cleanup tests.
- Test ordered multi-file execution, shared-session behaviour, fail-fast
  handling, and safe diagnostics.
- Test each runtime adapter against the core invariants it must preserve.
- Test credential-provider implementations independently from the core runner.
- Prove the same registrar installs a pure function and a connection-bound
  function with optional arguments without changing the runner.
- If a requested check cannot run because tooling is not scaffolded, report the
  exact gap in the handoff.

## Documentation

- Document public behaviour changes in `docs/`.
- Add Mermaid diagrams when they clarify execution flow, ownership, adapter
  boundaries, or state transitions.
- Keep examples concise and move extended examples to
  `docs/developer-examples.md`.

## Commits

- Do not commit unless the user asks.
- When committing, use Conventional Commits such as `feat:`, `fix:`, `docs:`,
  `test:`, `refactor:`, or `chore:`.
- Commit only intentional, reviewed changes. Do not include unrelated dirty
  work.
