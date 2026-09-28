# Shared Credentials And SFTP Filesystems

Status: **Complete**
Last updated: 2026-09-28
Epic: 04 Filesystems
Phase: 01
Related docs: [Credential Providers](../../credential-providers.md)

## Accepted Direction

Share provider selection, Prefect Block loading, and typed credential data
between `register_secret` and `register_filesystem`. Keep DuckDB secret
registration and filesystem construction in their respective function packages.
Preserve existing secret SQL calls, override behaviour, and Block import paths.

The first filesystem is SFTP with private-key credentials. Load optional
dependencies only when selected. Validate globbing directly and through DuckDB
before relying on this backend. Azure filesystem adapters remain future work.

## Validation

- Full suite: 135 passed with Prefect and SFTP extras installed.
- Strict Pyright: zero errors or warnings.
- Ruff, documentation links, and `git diff --check`: passed.
- Real loopback SFTP tests cover direct and recursive globbing, missing matches,
  SQL wildcard reads with four DuckDB threads, memory and disk databases,
  duplicate registration, and transport cleanup.
- Regression coverage includes every existing credential type, SQL overrides,
  aliases, safe errors, legacy Block imports and slugs, and installation without
  optional providers or filesystem dependencies.

## Implementation Notes

Shared loading returns credential data without registration methods. Secret
models retain the existing extension-loading and parameter-bound SQL behaviour.
Compatibility modules preserve the old Block import paths.

DuckDB can issue concurrent reads against the filesystem. Paramiko's shared
SFTP channel required serialized synchronous requests and non-pipelined
directory listings to avoid readers consuming each other's responses. This is
contained in the SFTP adapter; the runner and function installer are unchanged.

The MVP permits one SFTP endpoint per database instance and requires an existing
trusted SSH host key. Production endpoint validation remains environment-specific.
