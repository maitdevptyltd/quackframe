# Quackframe Epics

Epic phase files are implementor-facing. They track architecture boundaries,
scope, status, validation, and follow-ups without duplicating developer guidance
from the main documentation.

## Epic 01: MVP

- [00 Repository Foundation](01-mvp/00-repository-foundation.md)
- [01 Configuration And Database Lifecycle](01-mvp/01-configuration-and-database-lifecycle.md)
- [02 Ordered SQL Execution](01-mvp/02-ordered-sql-execution.md)
- [03 Developer Entry Points](01-mvp/03-developer-entry-points.md)
- [04 SQL Function Framework](01-mvp/04-sql-function-framework.md)
- [05 Runtime Adapter Boundary](01-mvp/05-runtime-adapter-boundary.md)
- [06 Prefect Runtime](01-mvp/06-prefect-runtime.md)
- [07 Credential Function Example](01-mvp/07-credential-function-example.md)

## Epic 02: Result Logging

- [01 SQL Result Logging](02-result-logging/01-sql-result-logging.md)

## Status Rules

Allowed statuses are `Planned`, `In Progress`, `Blocked`, and `Complete`.
Implementation begins only after the relevant architecture direction is
reviewed. A phase becomes complete only when its implementation, tests,
developer documentation, and applicable checks are complete.

## Related Docs

- [Roadmap](../roadmap.md): overall sequencing and acceptance criteria.
- [Documentation Index](../README.md): developer-facing knowledge map.
