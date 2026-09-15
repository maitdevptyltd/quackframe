# Credential Function Example

Status: **Planned**
Last updated: 2026-09-15
Epic: 01 MVP
Phase: 07
Related docs: [Credential Providers](../../credential-providers.md)

## Outcome

Prove the autonomous SQL-function extension model with optional MSSQL and Azure
connection-string registration.

## Scope

- Implement the `register_secret` function package.
- Select providers through the SQL function parameter.
- Keep provider contracts and registry local to the function.
- Add an optional Prefect Block provider.
- Support the public secret types `mssql` and `azure_connection_string`.
- Register Azure connection strings as scoped `TYPE azure`, `PROVIDER config`
  DuckDB secrets.
- Register temporary DuckDB secrets through bound values.
- Return only a non-sensitive outcome.

## Validation

- Test provider selection, references, aliases, and unsupported types.
- Test MSSQL credential translation and defaults.
- Test Azure connection-string validation, scope handling, extension loading,
  and parameter binding.
- Test direct execution with Prefect credentials.
- Test the Prefect runtime with and without credential registration.
- Verify credentials are absent from SQL results, logs, exceptions, arguments,
  and persistent Quackframe metadata.

## Open Decisions

- Whether the function ships in base Quackframe or an optional extra.
- Exact Azure scope schemes supported after DuckDB compatibility testing.
