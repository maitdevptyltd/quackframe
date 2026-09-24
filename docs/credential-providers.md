# Credential Providers

Credential resolution is one optional use case for Quackframe's SQL function
model. It is not a core goal, a required dependency, or the organising
abstraction of the execution engine.

## Intended SQL Contract

A generic function selects its provider per operation. The preferred call uses
the provider, credential reference, and secret type only:

```sql
SELECT quackframe.register_secret(
    'prefect',
    'reporting_sql_login',
    'mssql'
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

The referenced credential should normally contain every value needed for
registration. Quackframe derives the DuckDB alias from the reference, keeping
ordinary calls concise. `alias` and `overrides` are optional tools for cases
where the use case genuinely requires them, not routine configuration inputs.

Keeping the provider explicit permits one workflow to use more than one
provider. A repository-wide `credentials.provider` setting is not required.

The Prefect provider supports three secret types:

| `secret_type` | Resolved credential shape | DuckDB secret |
| --- | --- | --- |
| `mssql` | Host, database, user, password, and optional connection settings | `TYPE mssql` |
| `azure_connection_string` | Azure Storage connection string and a DuckDB-compatible scope | `TYPE azure`, `PROVIDER config` |
| `ssh_private_key` | Username, private-key path, port, and scope | `TYPE SSH` |

The public name uses `azure_connection_string` rather than an abbreviated
`azure_connection_str`. This leaves room for future Azure authentication
strategies without treating every Azure credential as a connection string.
Likewise, `ssh_private_key` identifies the supported SSH authentication
strategy while DuckDB still registers its extension-defined `TYPE SSH` secret.

## Prefect References And DuckDB Aliases

Prefect Block document names use lowercase letters, numbers, and dashes, while
Quackframe limits generated DuckDB secret aliases to simple SQL identifiers
using letters, numbers, and underscores. The Prefect provider bridges that
naming boundary in both directions:

- an underscored SQL reference such as `shared_sql_login` loads the Prefect
  Block document named `shared-sql-login`; and
- when `alias` is omitted, a dashed reference such as `shared-sql-login`
  registers the DuckDB secret alias `shared_sql_login`.

This translation deliberately treats dashed and underscored spellings as the
same Prefect reference. Prefect does not permit the underscored document-name
alternative, so the convenience does not collapse two valid Prefect names.
Other credential providers retain ownership of their own reference rules.

This lets DuckDB-oriented SQL use one identifier-safe spelling throughout:

```sql
SELECT quackframe.register_secret(
    'prefect',
    'shared_sql_login',
    'mssql'
);

ATTACH '' AS reporting (
    TYPE mssql,
    SECRET shared_sql_login
);
```

## Per-call Overrides

`overrides` is an optional escape hatch, not the preferred registration path.
Keep stable database, connection, and scope values in the credential document
and omit `overrides` from ordinary calls.

Use an override only when a concrete use case needs one stored authentication
credential to register different database- or scope-specific secrets per call.
The SQL-facing name reflects that narrow purpose rather than leaking the Python
term `kwargs` into the public API.

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
| `azure_managed_identity` | `scope` |
| `ssh_private_key` | `scope` |

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
- translating provider-specific reference naming rules at that boundary;
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

For Azure connection-string registration, the preferred Prefect Block contains
both the connection string and its scope. The model permits an omitted scope
only so an exceptional per-call override can supply it. The provider installs
and loads DuckDB's Azure extension as required, then creates a scoped temporary
secret using bound values. The connection string must never be interpolated
into generated SQL.

For Azure managed-identity registration, use `azure_managed_identity` with an
`AzureManagedIdentityCredentials` block containing `account_name`, optional
`client_id`, and optional `scope`. Scope must be supplied in the block or through
an override, using the same Azure URI validation as connection-string secrets.
Account and identity selection remain owned by the block. Registration loads
the Azure extension and creates a temporary `TYPE azure` secret with
`PROVIDER managed_identity`, binding all field values. `CLIENT_ID` is omitted
when unset so Azure can use the single available identity. Set it explicitly
when the environment has multiple identities, as described in the
[DuckDB Azure documentation](https://duckdb.org/docs/lts/core_extensions/azure#managed-identity).

For private-key SSH registration, the Prefect provider resolves a block
containing a protected username, private-key path, port, and required scope.
Reviewed SQL may replace only the scope, allowing one block to be narrowed to a
remote directory without moving authentication or connection settings into
SQL. The provider installs DuckDB's community `sshfs` extension and creates a
temporary `TYPE SSH` secret using bound values. Availability therefore depends
on the platforms for which that community extension publishes binaries.

## Prefect Block Ownership

Quackframe owns the Prefect Block classes expected by its provider. They live
inside the optional `register_secret` Prefect provider package so downstream
repositories do not have to reproduce Quackframe's credential schemas:

```text
sql_functions/register_secret/providers/prefect/
├── provider.py
└── blocks/
    ├── mssql.py
    ├── azure_connection_string.py
    ├── azure_managed_identity.py
    └── ssh_private_key.py
```

The MVP block shapes are conceptually shown below. Optional fields preserve the
supported override capability; they do not make overrides the preferred usage.

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


class AzureManagedIdentityCredentials(Block):
    account_name: str
    client_id: str | None = None
    scope: str | None = None


class SshPrivateKeyCredentials(Block):
    username: SecretStr
    key_path: str
    port: int = 22
    scope: str
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
