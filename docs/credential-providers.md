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

The Prefect provider supports four secret types:

| `secret_type` | Resolved credential shape | DuckDB secret |
| --- | --- | --- |
| `mssql` | Host, database, user, password, and optional connection settings | `TYPE mssql` |
| `azure_connection_string` | Azure Storage connection string and a DuckDB-compatible scope | `TYPE azure`, `PROVIDER config` |
| `azure_managed_identity` | Storage account, optional client ID, and scope | `TYPE azure`, `PROVIDER managed_identity` |
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
| `azure_managed_identity` | Storage account, optional client ID, and scope | `TYPE azure`, `PROVIDER managed_identity` |
| `ssh_private_key` | `scope` |

String values are parsed by the selected secret model before they are merged.
Precedence is per-call override, then provider value, then the model's
documented default. Required fields are validated after the merge.
Unknown keys and invalid values fail before DuckDB creates a secret.

Overrides are reviewed SQL, not a second credential channel. They must never
accept usernames, passwords, connection strings, tokens, or other
secret-bearing fields.

## Responsibility Boundary

Both `register_secret` and [register_filesystem](filesystems.md) select a strategy
from their own explicit allowlist, then use
`credential_loading.loading.load_credentials(provider, reference, model_type, overrides)`.
This shared path selects the provider, loads one concrete strategy and invokes
its inherited `resolve_overrides()`. It does not register anything or cache
credentials. Calling both SQL functions loads one Block per call.

The shared Pydantic models in `credential_loading/models.py` own typed fields,
validators, override allowlists, parsing and immutable resolution. Resolved
objects retain their concrete strategy type. MSSQL permits `database`, `port`
and `use_encrypt`; the Azure and SSH models permit only `scope`. Omitted, NULL
and empty maps preserve stored values. Invalid supplied values fail instead of
falling back. Authentication fields cannot be overridden.

Specialised strategies own their operations:

- `register_secret/models.py` implements `register_duckdb_secret(connection, alias)`,
  retaining extension loading and parameter-bound temporary-secret SQL.
- `register_filesystem/models.py` implements
  `create_filesystem(protocol)`, owning backend requirements, construction,
  endpoint/path translation and cleanup. The function registers the resulting
  adapter with DuckDB and the session resource owner.

Neither operation is required by the shared credential model. SQL
identifier validation lives in `sql_functions/validation.py`; the unchanged
Azure URI validation lives in `credential_loading/validation.py`.

Providers implement the generic contract
`resolve(reference, model_type: type[T]) -> T`, where `T` derives from
`CredentialModel`. The requested strategy declares a `credential_type`.
Providers return that strategy directly; they do not return an intermediate
model for later conversion. Provider failures must omit sensitive values.

### Python API

Import shared credential models from `quackframe.credential_loading.models`
and providers from `quackframe.credential_loading.providers`. Secret strategies
live in `quackframe.sql_functions.register_secret.models` and use the names
`MssqlSecret`, `AzureConnectionStringSecret`, `AzureManagedIdentitySecret` and
`SshPrivateKeySecret`.

Providers accept a concrete model class:

```python
from quackframe.credential_loading.providers.prefect.provider import (
    PrefectCredentialProvider,
)
from quackframe.sql_functions.register_secret.models import MssqlSecret

credentials = PrefectCredentialProvider().resolve("reporting_login", MssqlSecret)
```

SQL type-name selection belongs to each SQL function's strategy registry.
Providers construct the requested model directly, and register through
`credential_loading.providers.registry` without editing either SQL wrapper.

## Prefect Provider

The Prefect provider loads named Prefect Blocks for both SQL registration
functions. It should reuse the Prefect integration's resolved
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

Each SQL function selects its allowed strategy class before loading. The
Prefect provider maps its `credential_type` to one Block class and loads that
Block once. The Block's typed `to_credentials(model_type)` method rejects an
incompatible credential family and constructs the requested strategy directly
from explicitly named fields.

For Azure connection-string registration, the preferred Prefect Block contains
both the connection string and its scope. The model permits an omitted scope
only so an exceptional per-call override can supply it. The secret strategy installs
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
Reviewed SQL may replace only the scope without moving authentication or
connection settings into SQL. For fsspec, scope selects the endpoint and is not
a directory access restriction; see [Filesystems](filesystems.md). The secret
strategy installs DuckDB's community `sshfs` extension and creates a
temporary `TYPE SSH` secret using bound values. Availability therefore depends
on the platforms for which that community extension publishes binaries.

The SSH Block also accepts `host_key_fingerprint: str | None = None`. Only
`register_filesystem` enforces this optional OpenSSH SHA256 server fingerprint;
see [Filesystems](filesystems.md). `register_secret` logs a warning when a
nonblank fingerprint is provided and passes the same four existing fields to
SSHFS. Missing or blank fingerprints produce no warning. SQL cannot override
the fingerprint. Existing saved Blocks may omit the field; register the updated
Block class schema to expose the new field in Prefect when configuring it.

## Prefect Block Ownership

Quackframe owns the Prefect Block classes expected by its provider. They live
inside the optional shared credential provider package so downstream
repositories do not have to reproduce Quackframe's credential schemas:

```text
credential_loading/providers/prefect/
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
prefect block register --module quackframe.credential_loading.providers.prefect.blocks
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

## Provider Registry

`credential_loading/providers` owns the shared protocol and lazy registry.
Each entry records a public provider name, implementation loader and actionable
missing-dependency message. Adding a provider requires its implementation and
one registry entry, without credential-type branches in SQL wrappers or the
runner. Core imports remain independent of Prefect and fsspec.

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

- [Filesystems](filesystems.md): standard SFTP registration from the same Blocks.
- [SQL Function Extensions](python-extensions.md): function packaging and
  macro generation.
- [Configuration](configuration.md): native provider settings and safe TOML.
- [Runtime Adapters](runtime-adapters.md): why the Prefect runtime is separate.
- [Prototype Reference](mad-utilities-duckdb-reference.md): the implemented
  credential experiment that informs this design.
