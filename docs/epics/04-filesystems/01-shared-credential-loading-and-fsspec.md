# Shared Credential Loading And fsspec Filesystems

Status: **In Progress**
Last updated: 2026-09-28
Epic: 04 Filesystems
Phase: 01
Related docs: [Credential Providers](../../credential-providers.md), [SQL Function Extensions](../../python-extensions.md)

## Outcome And Authority

Enable SQL to register a standard fsspec filesystem with DuckDB using existing
credential Blocks, while preserving the existing model-owned strategy pattern.
The requested separation is loading followed by registration. Shared models
retain their behaviour. Before the first release, the repository has one current
API: superseded imports, credential aliases and string-based provider calls are
removed. The `register_secret` SQL contract and behaviour remain unchanged.

Implementation was authorised on 2026-09-28 by the request to implement this
scope on `feat/fsspec-filesystems`. The fresh branch
is `feat/fsspec-filesystems`, based on `feat/setup` at
`8d0841eafe8b9211896daddd0d6a418e11cd390a`. Do not cherry-pick the prior filesystem
implementation. The prior branch and its uncommitted changes remain separate.

User requirements governing this scope:

- Each SQL function keeps its own folder.
- Both functions use one shared loading implementation.
- Preserve Pydantic models, inheritance, validation, overrides, and strategy dispatch.
- Put as much type-specific behaviour as possible on the individual Blocks/models.
- Use DuckDB's existing filesystem registration API and standard fsspec objects.
- The user will test SFTP globbing and DuckDB file reads after implementation.
  No preliminary filesystem feasibility test is required.

## Baseline To Preserve

This section describes the historical starting implementation on `feat/setup`,
not the proposed registration method names or ownership:

- `register_secret/function.py` validates the alias, selects a provider, calls
  `resolve(reference, secret_type)`, invokes the returned model's
  `resolve_overrides()`, and calls its `register()` through a duplicate connection.
- `register_secret/models.py` contains `DuckDBSecret(BaseModel, ABC)` and concrete
  MSSQL, Azure connection-string, Azure managed-identity, and SSH private-key
  strategies.
- The base model centralizes the override-key check. Concrete models own their
  fields, field validators, allowlists, parsing, override resolution, and secret
  registration. `resolve_overrides()` preserves the concrete model type.
- `providers/registry.py` lazily selects credential providers. Prefect is optional.
- The Prefect provider loads one Block document, translates its fields explicitly,
  and returns a concrete strategy. It also owns underscore-to-dash reference
  translation and safe load failures.
- `validation.py` contains two different responsibilities: SQL identifier
  validation and Azure credential scope validation. Neither is inherently a
  secret-only concern.

Tests in [test_register_secret.py](../../../tests/test_register_secret.py) and
[test_prefect_integration.py](../../../tests/test_prefect_integration.py) protect
these behaviours. Preserve their assertions; do not replace them with mocks of
new conversion machinery just to make a restructuring pass.

## Ownership: Behaviour Belongs On The Individual Models

There are two existing kinds of model. Keep their roles explicit:

1. Prefect `Block` subclasses describe stored documents and require Prefect.
2. Quackframe Pydantic strategy models describe validated credentials and behaviour
   without requiring Prefect.

A shared credential model must remain behavioural. Move its existing field
validators, override allowlist, parsing helpers, and `resolve_overrides()` with
its fields. Do not move only the fields and leave the methods behind.

| Responsibility | Owner |
| --- | --- |
| Shared override-key enforcement and model contract | Common credential base model |
| MSSQL database, port, encryption parsing and defaults | Individual MSSQL credential model |
| Azure connection-string validation and scope resolution | Individual Azure connection-string model |
| Azure identity selection validation and scope resolution | Individual Azure managed-identity model |
| SSH username/key/port fields and scope override | Individual SSH credential model |
| Azure scope helper used by both Azure models | Shared credential validation module |
| Prefect document schema and explicit field translation | Individual Prefect Block class |
| Provider lookup, reference normalization, loading failure boundary | Shared provider infrastructure |
| Secret SQL, extension loading, bound parameters | Individual secret registration strategy |
| fsspec constructor arguments and backend-specific requirements | Individual filesystem registration strategy |
| SQL identifier syntax | Shared SQL validation module |
| SQL invocation coordination | Each function's own `function.py` |

Specific logic must not migrate into a large shared loader. For example, an SSH
strategy owns translating `key_path` to the standard backend's key-file argument;
the loader must not know what an SSH key is. Likewise, MSSQL boolean parsing must
stay on its credential model rather than becoming a provider or SQL-wrapper branch.

Do not add a validation framework or generic merge engine. Extract and inherit
the working methods already present. Keep the exact current validation semantics
unless a separately documented change is approved.

## Directory Structure

```text
src/quackframe/
  credential_loading/
    __init__.py
    loading.py
    models.py
    validation.py
    providers/
      __init__.py
      protocol.py
      registry.py
      prefect/
        __init__.py
        provider.py
        blocks/
          __init__.py
          mssql.py
          azure_connection_string.py
          azure_managed_identity.py
          ssh_private_key.py
  sql_functions/
    __init__.py
    definition.py
    installer.py
    registry.py
    validation.py
    register_secret/
      __init__.py
      function.py
      models.py
    register_filesystem/
      __init__.py
      function.py
      models.py
```

The tree shows the canonical implementation and import paths. Do not retain
forwarding modules at superseded paths or aliases for removed model names.
Do not create per-type files merely to expand the tree.
Keep the existing model grouping unless its size warrants a separately reviewed split.

### Exact extraction boundaries

- `credential_loading/models.py`: extract the common credential base and concrete
  credential parents, including all existing fields, validators, allowlists,
  `validate_override_keys()`, `resolve_overrides()`, and parsing helpers.
- `credential_loading/validation.py`: move `validate_azure_scope()` unchanged.
  Its current DuckDB-compatible URI rules are preserved; they are not a claim
  that every future Azure library accepts the same URI syntax.
- `sql_functions/validation.py`: move `validate_identifier()` unchanged.
- `register_secret/models.py`: retain the existing concrete secret strategies and
  registration bodies under `register_duckdb_secret(connection, alias)`. They
  inherit the extracted credential behaviour instead of reimplementing it.
  The secret-specific abstract contract belongs in this module, not on the
  shared credential base. Concrete strategy names end in `Secret`; credential
  parents live in the shared module. The operation is `register_duckdb_secret()`.
- `register_filesystem/models.py`: introduce the filesystem registration contract
  and SFTP strategy, inheriting the same SSH credential parent. Its
  `register_filesystem_protocol(connection)` method owns standard filesystem
  construction and invokes DuckDB registration. The filesystem-specific abstract
  contract belongs in this module, not on the shared credential base.
- Shared providers retain lazy imports and their existing provider registry.
  Individual Prefect Blocks own explicit conversion of their own fields into the
  requested compatible strategy model.

The important SSH relationship is:

```text
Shared SSH credential model: fields + validators + allowed overrides + resolution
  -> SshPrivateKeySecret: register_duckdb_secret(connection, alias)
  -> SftpFilesystem: register_filesystem_protocol(connection)
```

Both subclasses inherit the same override implementation. Neither function has
an SFTP-specific free-standing `resolve_overrides()` helper.

### Required registration methods and ownership

- Specialised secret blocks implement
  `register_duckdb_secret(connection, alias)` in `register_secret/models.py`.
- Specialised filesystem blocks implement
  `register_filesystem_protocol(connection)` in `register_filesystem/models.py`.
- The shared credential base and shared credential parents implement neither
  registration method and declare neither as an abstract requirement. They own
  shared fields, validation, and overrides only.
- A secret subclass is not required to implement filesystem registration, and
  a filesystem subclass is not required to implement secret registration.
- `register_secret/function.py` calls the loaded specialised block's
  `register_duckdb_secret(...)`; `register_filesystem/function.py` calls the
  loaded specialised block's `register_filesystem_protocol(...)`.
- There is one operation-specific registration implementation per specialised
  block. Do not add a generic `register()` implementation, forwarding registration
  aliases, or duplicate registration logic to the shared models or loader.

These names and ownership rules are user-directed requirements, not open design
choices. Preserve the existing secret registration behaviour while moving its
method body to the explicitly named operation.


## Loading Contract And Strategy Selection

The shared loading operation is conceptually:

```text
load_credentials(provider, reference, model_type, overrides) -> same concrete model type
```

Its complete job is to select the provider, ask it to construct the requested
strategy from the referenced Block, invoke the model's `resolve_overrides()`, and
return that resolved strategy. It does not register anything.

The provider contract should be generic in the requested credential model type:
`resolve(reference, model_type: type[T]) -> T`, where T derives from the shared
credential base. This is the only provider call format. SQL type-name selection
occurs in the function registry before loading.

Each concrete strategy declares its credential type as class metadata. Each SQL
function's model module owns an explicit allowlist of its supported strategy
classes. Selection by the SQL type name happens once at that boundary. The shared
loader and runner do not acquire credential-type conditionals.

The Prefect provider maps the selected model's credential type to the matching
Block class. A Block-local conversion method receives the compatible target
model class and constructs it directly from explicitly named fields. The Block
binding must reject an incompatible model family before constructing it. Keep
this conversion typed; do not pass unrestricted `Any` payloads between layers.

This preserves direct strategy dispatch while sharing the external load:

1. Function selects an allowed strategy class.
2. Shared loader selects the provider.
3. Provider loads the matching Block once.
4. That Block constructs the requested concrete model directly.
5. Shared loader calls the model's inherited override method.
6. The secret function invokes `register_duckdb_secret(connection, alias)`;
   the filesystem function invokes `register_filesystem_protocol(connection)`.

There is no intermediate data-only credential instance, no `model_dump()` round
trip to convert one model into another, and no `secret_from_credentials()` or
`isinstance` dispatcher. Existing `model_dump()` calls inside the established
immutable override resolution remain valid; do not remove working model logic
merely because the same method name appeared in the rejected conversion design.

Loading twice when SQL calls both functions is acceptable. Sharing code does not
imply a credential cache. Caching, global state, and SQL-visible load handles are
outside this scope.

## SQL Contracts

The existing secret function remains exactly:

```sql
SELECT quackframe.register_secret(
    'prefect', 'reporting_login', 'mssql',
    alias := 'reporting',
    overrides := MAP {'database': 'Reporting'}
);
```

Preserve argument order, named arguments, default alias derivation, nullable
optional arguments, boolean result, and `MAP(VARCHAR, VARCHAR)` overrides.

Approved filesystem interface:

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'source_files', 'sftp',
    overrides := MAP {'scope': 'sftp://files.example.test/'}
);
```

The filesystem name selects `SftpFilesystem`; that strategy declares
`ssh_private_key` as its credential type. The generic wrapper does not hardcode
that mapping. The filesystem function has no secret alias argument: DuckDB's
filesystem registration accepts a filesystem object, not a secret alias.

Query paths use the backend's standard protocol, for example
`sftp://files.example.test/reports/*.csv`. Scope review confirmed that no
`quack://` protocol or custom directory-root wrapper will be added.

The initial override rules are inherited unchanged:

| Credential model | Allowed overrides |
| --- | --- |
| MSSQL | `database`, `port`, `use_encrypt` |
| Azure connection string | `scope` |
| Azure managed identity | `scope` |
| SSH private key | `scope` |

For each function, omitted, NULL, and empty maps keep existing values. A supplied
value takes precedence; an invalid supplied value must not silently fall back.
Unknown keys and authentication overrides are rejected by the model. Neither
loaded models nor saved Blocks are mutated. Backend-specific endpoint checks
belong to the concrete registration strategy, after shared override resolution.

Only SFTP filesystem delivery is in the first implementation. Existing Azure and
MSSQL secret support must remain functional. Future Azure filesystem strategies
must inherit the existing Azure credential behaviour without editing the generic
loader or either SQL wrapper; adding them is not part of this scope.

## Explicit Exclusions

Do not introduce any of the following under this scope:

- `SerializedSFTPClient`, `ManagedSFTPFileSystem`, or equivalents.
- Overrides of Paramiko `_request()` or fsspec `_connect()`.
- Custom connection pools, thread locks, request queues, finalizer frameworks,
  host-routing layers, or SSH trust-policy implementations.
- Duplicate provider loading or duplicate override/validation implementations.
- A shared models package stripped of its existing behaviour.
- Credential-type branches in the SQL runner or function installer.
- Unreviewed changes to existing secret field requirements or SQL behaviour.
- Automatic fallback from one backend to another.
- A new filesystem alias scheme or assumptions about multi-server routing.

If a supported library cannot meet a necessary requirement without one of these
changes, the scope must return for review. Passing tests does not authorize a
change to these architecture constraints.

## Delivery Sequence And Review Points

### 1. Establish the baseline

After implementation approval, run the baseline suite on `feat/setup`, record
any environmental failures separately, and identify the existing assertions for
all four credential types. Capture public model imports and Prefect Block schema
identity before moving classes. Use Poetry only.

### 2. Extract shared loading and model behaviour

Move common behaviour and its validators together. Adapt provider construction to
return the selected concrete strategy directly. Retain secret registration method
bodies under `register_duckdb_secret()` and update imports to canonical owners.
Review this diff independently before adding filesystem
registration. It must contain no new SSH transport behaviour.

### 3. Add the filesystem strategy and SQL function

Add the SFTP strategy and its thin SQL wrapper. Register it through the existing explicit `SqlFunction` registry with
connection binding, side effects, and optional-map handling. Keep optional
filesystem dependencies behind the selected strategy and in a Poetry extra.

### 4. Validate behaviour and architecture

Run the full suite with optional integrations installed, focused optional-
dependency absence checks, Ruff, Pyright, documentation links, and diff checks.
Review the source as well as the test results. Do not commit or publish without
an explicit request.

## Required Acceptance Evidence

| Area | Evidence required |
| --- | --- |
| Secret SQL behaviour | Existing positional/named calls, aliases, extension loading, temporary-secret SQL and bound parameter values remain unchanged |
| Models | Original validators/defaults and override semantics remain on common parents; concrete strategy type survives overrides |
| Overrides | Valid, invalid, blank, omitted, NULL and empty-map cases; forbidden keys; no mutation; safe diagnostics |
| Shared loading | Both functions use the same provider path; one Block load per call; a concrete requested strategy is returned directly |
| Prefect Blocks | Canonical shared imports; correct Block names, slugs, fields and model construction |
| Provider extensibility | An additional test provider works without edits to the generic SQL wrappers |
| Strategy extensibility | A second test filesystem strategy works through class registration without SFTP branches in the wrapper |
| Standard SFTP | User-run verification of globbing, DuckDB reads, concurrency and cleanup after implementation |
| Optional dependencies | Core and secret-only execution work without Prefect/fsspec/Paramiko; selecting a missing integration gives an actionable safe error |
| SQL framework | Existing installer, connection binding, ordered execution, failure and cleanup semantics remain intact |
| Architecture | Registration methods exist only on specialised blocks: `register_duckdb_secret()` for secrets and `register_filesystem_protocol()` for filesystems; neither lives on the shared credential base. No duplicate overrides, conversion dispatcher, or custom transport subclasses |

New tests should exercise behaviour, not merely assert implementation structure.
The architecture review additionally verifies that the expected shared methods
are actually inherited and that no prohibited workaround was introduced.

## Implementation And Verification

Implementation is complete on `feat/fsspec-filesystems`; the phase remains
**In Progress** for the user-run live SFTP checks required above. Changes remain
uncommitted for review.

- The baseline at `8d0841e` passed all 119 tests. Initial sandbox temporary-file
  permission failures were resolved by running with permitted filesystem access
  and an explicit local pytest temporary directory.
- Shared model fields, validators, allowlists, parsing and override methods were
  extracted together. Secret SQL bodies remain unchanged apart from the required
  method name. Regression tests exercise the concrete strategies and SQL calls.
- All four Prefect Block JSON schemas, names, slugs and schema checksums were
  captured before moving classes and compared afterward: unchanged. Blocks and
  providers have one canonical import location under `credential_loading`.
- The shared provider contract uses the requested concrete model type. Each
  Prefect Block owns explicit field translation and checks model-family
  compatibility before construction. Providers accept only a concrete model
  class. There are no string-call overloads, obsolete import modules or secret
  model aliases.
- `register_filesystem` uses the ordinary descriptor registry and shared loader.
  `SftpFilesystem` inherits SSH override behavior and registers the standard
  backend. Core runner, installer and execution semantics are unchanged.
- The `sftp` Poetry extra contains fsspec and Paramiko. The updated lockfile and
  installed optional integrations are consistent.
- Automated tests cover SQL optional arguments, safe failures, immutable models,
  one Block load per call, additional provider/strategy registration and core
  execution with optional imports blocked. A standard in-memory backend verifies
  a DuckDB CSV glob read across ordered SQL files and native duplicate rejection.
- First-release API validation: 157 tests passed with the locked optional
  integrations installed. Pyright reported zero errors or warnings, and
  full-repository Ruff passed. Markdown links and diff checks passed. The test
  for obsolete import re-exports was removed; SQL behaviour assertions remain.
- Standard SFTP endpoint/path interpretation, native duplicate-registration
  behavior and ownership are documented in [Filesystems](../../filesystems.md).
  Scope provides the host; its directory is not an enforced access boundary.
  The Block owns the port. No endpoint registry or custom transport was added.

Live SFTP globbing, DuckDB reads, concurrency and socket cleanup remain for the
user. They are not established by mocked connection tests or the in-memory
filesystem integration. If standard library behavior requires a custom transport
or finalizer framework, return that change to scope review.

## Related Docs

- [Credential Providers](../../credential-providers.md): shared models and provider contracts.
- [Filesystems](../../filesystems.md): SQL usage, endpoint interpretation and ownership.
- [SQL Function Extensions](../../python-extensions.md): function-owned packages and registration.
- [Execution Lifecycle](../../execution-lifecycle.md): session ownership and ordered SQL.
- [Credential Function Example](../01-mvp/07-credential-function-example.md): original strategy implementation scope.
