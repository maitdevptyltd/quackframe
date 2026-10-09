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

## Epic 03: Configuration

- [01 Dotenv Configuration Loading](03-configuration/01-dotenv-loading.md)

## Epic 04: Filesystems

- [01 Shared Credential Loading And fsspec](04-filesystems/01-shared-credential-loading-and-fsspec.md)
- [02 Named Filesystem Protocol Registrations](04-filesystems/02-aliased-filesystem-registrations.md): named protocols and independent backend lifetimes.
- [03 Azure Filesystem Strategies](04-filesystems/03-azure-filesystem-strategies.md): planned Blob and ADLS Gen2 reads using existing Azure credential Blocks.
- [04 Filesystem Write Support](04-filesystems/04-filesystem-write-support.md): writes across SFTP and both Azure strategies, with live validation outstanding.

## Epic 05: Releases

- [01 Semantic Versioning And Package Publication](05-releases/01-semantic-versioning-and-publication.md): automatic RCs from `release/next`, promotion to `main`, and direct stable patches; external activation outstanding.

## Epic 06: Prefect Deployment

- [01 Prefect Deployment Entry Point](06-prefect-deployment/01-deployment-entry-point.md): public Quackframe flow, native Prefect deployment, and execution-environment SQL paths, with validation evidence.

## Epic 07: Parameterized SQL

- [01 Parameter Binding And SQL Invocation](07-parameterized-sql/01-parameter-binding-and-sql-invocation.md): proposed common parameter execution and two public entry points.

## Status Rules

Allowed statuses are `Planned`, `In Progress`, `Blocked`, and `Complete`.
Implementation begins only after the relevant architecture direction is
reviewed. A phase becomes complete only when its implementation, tests,
developer documentation, and applicable checks are complete.

## Related Docs

- [Roadmap](../roadmap.md): overall sequencing and acceptance criteria.
- [Documentation Index](../README.md): developer-facing knowledge map.
