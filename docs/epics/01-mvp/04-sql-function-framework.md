# SQL Function Framework

Status: **Complete**
Last updated: 2026-09-16
Epic: 01 MVP
Phase: 04
Related docs: [SQL Function Extensions](../../python-extensions.md)

## Outcome

Install self-contained Python functions behind clear, collision-resistant SQL
names.

## Scope

- Define the minimal signature-aware `SqlFunction` descriptor.
- Inspect supported parameters and type annotations and fail unsupported
  definitions before SQL execution.
- Bind the active DuckDB connection for functions that request it while hiding
  that parameter from SQL.
- Install built-ins from one explicit registry through a function-neutral
  registrar.
- Register connection-scoped `_quackframe_<name>` Python UDFs.
- Create public `quackframe.<name>` macros.
- Support optional Python parameters through generated macro defaults.
- Validate names, types, null handling, and side effects.
- Establish one function-owned package per non-trivial function.

## Design Rules

- Functions share only the minimal framework contract.
- Duplication is preferable to restrictive coupling.
- Themes are metadata or documentation categories, not forced implementation
  ownership.
- Installing a package must not silently expose unapproved SQL functions.
- The registrar and runner must not branch on function names, providers, or
  function-specific request types.
- Automatic external discovery is not part of the MVP.

## Validation

- Test public macro calls and private UDF isolation.
- Test optional parameters, invalid definitions, and duplicate names.
- Prove the unchanged registrar installs both a pure function and a
  connection-bound function with an optional argument.
- Prove adding either function requires no runner change.
- Run core registrar tests without Prefect installed.
- Test persistent-database reconnection and macro recreation.
- Prove one function can fail registration without corrupting other definitions.

## Open Decisions

- Post-MVP external function entry-point discovery and allowlisting contract.
- Persisted macro cleanup and compatibility policy.

The MVP validates all enabled definitions before making catalog changes and
installs macros transactionally. Enabled persistent macros are replaced during
each connection setup.

The supported scalar annotation map is a named module-level framework boundary.
Optional dependencies selected within a function are checked by that function's
adapter rather than attached to the generic function definition.
