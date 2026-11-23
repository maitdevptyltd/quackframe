# Runtime Adapter Boundary

Status: **Complete**
Last updated: 2026-09-16
Epic: 01 MVP
Phase: 05
Related docs: [Runtime Adapters](../../runtime-adapters.md)

## Outcome

Allow external runtimes to represent Quackframe runs without owning
core execution semantics.

## Scope

- Define the minimal runtime adapter contract.
- Implement direct execution.
- Keep framework-specific types out of core models and exceptions.
- Establish adapter conformance tests for ordering, session, failure, and
  lifecycle behaviour.

## Validation

- Run core and direct-runtime tests without optional integrations installed.
- Prove adapter selection cannot silently add retries, caching, concurrency, or
  file reordering.
- Verify missing optional dependencies fail before SQL execution.

The direct adapter imports no optional framework. Runtime selection occurs
before a DuckDB session opens, and missing Prefect support produces an
actionable optional-dependency error.

One explicit registry now owns runtime names, lazy implementation loading, and
missing-dependency messages. Configuration validation and CLI choices consume
the same names.
