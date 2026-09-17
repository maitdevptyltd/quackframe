# Credential Function Example

Status: **Complete**
Last updated: 2026-09-17
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
- Define the Prefect Block classes inside the optional provider package and
  document their registration with Prefect.
- Translate SQL-friendly underscore references to Prefect's required dashed
  document names while deriving underscore-safe DuckDB aliases from dashed
  references.
- Support the public secret types `mssql` and `azure_connection_string`.
- Accept an optional `MAP(VARCHAR, VARCHAR)` named `overrides`.
- Allow MSSQL `database`, `port`, and `use_encrypt` overrides and Azure `scope`
  overrides; reject all other keys.
- Register Azure connection strings as scoped `TYPE azure`, `PROVIDER config`
  DuckDB secrets.
- Register temporary DuckDB secrets through bound values.
- Return only a non-sensitive outcome.

## Validation

- Test provider selection, references, aliases, and unsupported types.
- Test the Prefect-reference and DuckDB-alias naming translation in both
  directions.
- Test MSSQL credential translation and defaults.
- Test Azure connection-string validation, scope handling, extension loading,
  and parameter binding.
- Test override precedence, type conversion, unknown keys, prohibited sensitive
  keys, and missing required post-merge fields.
- Test one MSSQL block registering secrets for multiple databases.
- Test direct execution with Prefect credentials.
- Test the Prefect runtime with and without credential registration.
- Verify credentials are absent from SQL results, logs, exceptions, arguments,
  and persistent Quackframe metadata.

## Open Decisions

- Additional provider entries remain post-MVP and are added only for concrete
  integration needs.
- MVP Azure scopes accept `az://`, `azure://`, and `abfss://` URIs with a
  trailing slash. Broader compatibility remains post-MVP work.

The provider registry now lazily loads each implementation and its optional
dependency. Providers return a provider-independent `DuckDBSecret`; each
concrete secret model owns its fields, safe override resolution, DuckDB
extension loading, and parameter-bound temporary registration. The generic
function contains no secret-type dispatcher and no global Prefect requirement.
The shared provider contract accepts a plain secret-type name; supported names
and conversions belong to each provider rather than a central type list.
