# Credential Providers

Credential resolution is one optional use case for Quackframe's SQL function
model. It is not a core goal, a required dependency, or the organising
abstraction of the execution engine.

## Intended SQL Contract

A generic function selects its provider per operation:

```sql
SELECT quackframe.register_secret(
    'prefect',
    'reporting-reader',
    'mssql',
    'reporting_reader'
);
```

The arguments are conceptually:

```text
register_secret(provider, reference, secret_type, alias := NULL)
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

## Responsibility Boundary

The `register_secret` function owns:

- validating provider, reference, secret type, and alias;
- selecting an installed provider implementation;
- asking that provider to register a DuckDB secret;
- returning a non-sensitive outcome; and
- converting failures into safe diagnostics.

A credential provider owns:

- resolving its reference through the external service;
- translating the resolved fields into the requested DuckDB secret type;
- using parameter binding rather than SQL interpolation;
- keeping sensitive values out of returned results and logs; and
- respecting provider-native authentication and configuration.

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

For Azure connection-string registration, the Prefect provider resolves a block
containing the connection string and its scope. It installs and loads DuckDB's
Azure extension as required, then creates a scoped temporary secret using bound
values. The connection string must never be interpolated into generated SQL.

## Security Rules

- SQL receives references and aliases, never credential values.
- Credentials must not appear in checked-in TOML, SQL, process arguments,
  normal logs, exceptions, or persisted Quackframe metadata.
- DuckDB secrets created through this function are temporary unless a separate
  reviewed contract explicitly allows persistence.
- Provider and database permissions remain the security boundary.
- SQL files are trusted operational code and require appropriate review.
- Private API URLs and other sensitive metadata remain in native profiles or
  environment configuration.

## Function Autonomy

`register_secret` owns its provider protocol and registry within its own
function package. Other SQL functions do not have to adopt those abstractions.
If another function later needs similar provider behaviour, duplication is
acceptable until a genuinely shared invariant earns extraction.

## Connection Mutation

The reviewed prototype demonstrates immediate secret registration through a
short-lived duplicate of the active DuckDB connection. This avoids queuing a
credential-specific request for the runner to process after the current SQL
statement and keeps the runner function-neutral.

Quackframe should use that approach only after compatibility tests confirm that
temporary secrets created through the duplicate connection are visible to the
job connection in every supported database mode and DuckDB version. If the
mechanism changes, the alternative must remain owned by `register_secret` and
must not introduce provider-specific behaviour into the core runner.

## Open Decisions

- The exact provider protocol and secret-type metadata contract.
- Which credential provider packages ship in the initial distribution.
- Whether `register_secret` itself is part of base Quackframe or an optional
  function extra.
- The naming and validation rules for default aliases.
- The precise Azure scope schemes accepted by the MVP after DuckDB compatibility
  testing.

## Related Docs

- [SQL Function Extensions](python-extensions.md): function packaging and
  macro generation.
- [Configuration](configuration.md): native provider settings and safe TOML.
- [Runtime Adapters](runtime-adapters.md): why the Prefect runtime is separate.
- [Prototype Reference](mad-utilities-duckdb-reference.md): the implemented
  credential experiment that informs this design.
