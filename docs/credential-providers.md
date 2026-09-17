# Credential Providers

Credential resolution is one optional use case for Quackframe's SQL function
model. It is not a core goal, a required dependency, or the organising
abstraction of the execution engine.

## Intended SQL Contract

A generic function selects its provider per operation:

```sql
SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'reporting_reader',
    overrides := MAP {'database': 'Reporting'}
);
```

The arguments are conceptually:

```text
register_secret(
    provider,
    reference,
    secret_type,
    alias := NULL,
    overrides := NULL
)
```

This keeps provider choice visible in reviewed SQL and permits one workflow to
use more than one provider. A repository-wide `credentials.provider` setting is
not required.

The MVP supports two secret types:

| `secret_type` | Resolved credential shape | DuckDB secret |
| --- | --- | --- |
| `mssql` | Host, database, user, password, and optional connection settings | `TYPE mssql` |
| `azure_connection_string` | Azure Storage connection string and a DuckDB-compatible scope | `TYPE azure`, `PROVIDER config` |

The public name uses `azure_connection_string` rather than an abbreviated
`azure_connection_str`. This leaves room for future Azure authentication
strategies without treating every Azure credential as a connection string.

## Per-call Overrides

`overrides` is an optional `MAP(VARCHAR, VARCHAR)`. The SQL-facing name reflects
its purpose rather than leaking the Python term `kwargs` into the public API.
It lets one stored credential supply authentication for multiple databases or
storage scopes.

This shape follows DuckDB's documented [MAP type and literal syntax](https://duckdb.org/docs/stable/sql/data_types/map)
and keeps the SQL-to-Python boundary explicit.

For example, the same MSSQL block can register two temporary secrets:

```sql
SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'reporting_reader',
    overrides := MAP {'database': 'Reporting'}
);

SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'warehouse_reader',
    overrides := MAP {'database': 'Warehouse'}
);
```

Each concrete secret model owns an allowlist and typed parser:

| Secret type | Allowed override keys |
| --- | --- |
| `mssql` | `database`, `port`, `use_encrypt` |
| `azure_connection_string` | `scope` |

String values are parsed by the selected secret model before they are merged.
Precedence is per-call override, then provider value, then the model's
documented default. Required fields are validated after the merge.
Unknown keys and invalid values fail before DuckDB creates a secret.

Overrides are reviewed SQL, not a second credential channel. They must never
accept usernames, passwords, connection strings, tokens, or other
secret-bearing fields.

## Responsibility Boundary

The `register_secret` function owns:

- validating the alias used in generated SQL;
- selecting an installed provider implementation;
- asking that provider for a provider-independent `DuckDBSecret` model;
- asking that model to resolve allowlisted overrides and register itself;
- returning a non-sensitive outcome; and
- converting failures into safe diagnostics.

A credential provider owns:

- resolving its reference through the external service;
- deciding which secret-type names it supports;
- explicitly translating the resolved fields into the requested Quackframe
  secret model;
- rejecting secret types for which it has no explicit conversion;
- loading only the optional dependencies required by that provider; and
- keeping sensitive values out of returned results and errors.

A concrete `DuckDBSecret` model owns:

- its typed credential fields;
- its allowlisted override parsing and final validation;
- required DuckDB extension loading;
- temporary-secret registration using bound values rather than SQL
  interpolation;
- keeping sensitive values out of returned results and logs; and
- its secret-type-specific error messages.

Project SQL owns which references it requests and how registered DuckDB secrets
are used in later `ATTACH`, file access, or other operations.

## Prefect Provider

The first provider is expected to load named Prefect Blocks and register
temporary DuckDB secrets. It should reuse the Prefect integration's resolved
client settings whether or not the Prefect runtime adapter is selected.

These combinations remain valid:

| Runtime | Credential provider |
| --- | --- |
| Direct | None |
| Direct | Prefect |
| Prefect | None |
| Prefect | Prefect |

Using Prefect credentials must not require the Prefect runtime, and the Prefect
runtime must not require credential registration.

The generic `register_secret` SQL function has no global Prefect dependency.
Provider dependencies are checked only after SQL selects a provider. A future
non-Prefect provider can therefore install and run without Prefect present.

The generic function passes the requested secret-type name to the selected
provider as plain text. There is no central list of MSSQL, Azure, or future
secret types. Each provider rejects names it does not explicitly support, and
each returned secret model owns its own type-specific behaviour.

For Azure connection-string registration, the Prefect provider resolves a block
containing the connection string and an optional scope. The scope must be
present either in the block or in the allowed per-call overrides. The provider
installs and loads DuckDB's Azure extension as required, then creates a scoped
temporary secret using bound values. The connection string must never be
interpolated into generated SQL.

## Prefect Block Ownership

Quackframe owns the Prefect Block classes expected by its provider. They live
inside the optional `register_secret` Prefect provider package so downstream
repositories do not have to reproduce Quackframe's credential schemas:

```text
sql_functions/register_secret/providers/prefect/
├── provider.py
└── blocks/
    ├── mssql.py
    └── azure_connection_string.py
```

The MVP block shapes are conceptually:

```python
class MssqlCredentials(Block):
    host: str
    user: SecretStr
    password: SecretStr
    database: str | None = None
    port: int = 1433
    use_encrypt: bool = True


class AzureConnectionStringCredentials(Block):
    connection_string: SecretStr
    scope: str | None = None
```

Quackframe stores no block documents or credential values. Prefect stores the
registered block types and saved documents; consuming SQL stores only document
references and non-sensitive overrides. The classes are available only with the
optional Prefect dependency installed.

Users can register the Quackframe block types so they are available through the
Prefect UI:

```powershell
prefect block register --module quackframe.sql_functions.register_secret.providers.prefect.blocks
```

Prefect distinguishes the local Python class, the server-registered block type,
and saved block documents. See Prefect's [Blocks](https://docs.prefect.io/v3/concepts/blocks)
and [custom block registration](https://docs.prefect.io/v3/advanced/custom-blocks)
documentation.

## Security Rules

- SQL receives references and aliases, never credential values.
- Credentials must not appear in checked-in TOML, SQL, process arguments,
  normal logs, exceptions, or persisted Quackframe metadata.
- Secret-bearing fields are never valid per-call overrides.
- DuckDB secrets created through this function are temporary unless a separate
  reviewed contract explicitly allows persistence.
- Provider and database permissions remain the security boundary.
- SQL files are trusted operational code and require appropriate review.
- Private API URLs and other sensitive metadata remain in native profiles or
  environment configuration.

## Function Autonomy

`register_secret` owns its provider protocol and registry within its own
function package. Each provider registry entry records its public name, lazy
implementation loader, and actionable missing-dependency message. Adding a
provider requires a provider package and one entry rather than a new branch in
the generic selector.

Other SQL functions do not have to adopt those abstractions. If another
function later needs similar provider behaviour, duplication is acceptable
until a genuinely shared invariant earns extraction.

## Connection Mutation

The reviewed prototype demonstrates immediate secret registration through a
short-lived duplicate of the active DuckDB connection. This avoids queuing a
credential-specific request for the runner to process after the current SQL
statement and keeps the runner function-neutral.

The MVP implements that approach inside `register_secret`. Tests cover the
duplicate-connection boundary and parameter-bound model calls. Live
credential and extension smoke tests remain environment-specific release
validation. Any future mechanism must remain owned by `register_secret` and
must not introduce provider-specific behaviour into the core runner.

## Post-MVP Decisions

- Whether additional credential providers earn inclusion.
- Whether credential functions move to their own distribution.
- Whether additional Azure scope schemes should be accepted.

## Related Docs

- [SQL Function Extensions](python-extensions.md): function packaging and
  macro generation.
- [Configuration](configuration.md): native provider settings and safe TOML.
- [Runtime Adapters](runtime-adapters.md): why the Prefect runtime is separate.
- [Prototype Reference](mad-utilities-duckdb-reference.md): the implemented
  credential experiment that informs this design.
