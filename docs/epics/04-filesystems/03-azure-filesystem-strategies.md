# Azure Filesystem Strategies

Status: **In Progress**
Last updated: 2026-10-01
Epic: 04 Filesystems
Phase: 03
Related docs: [Filesystems](../../filesystems.md), [Credential Providers](../../credential-providers.md), [Named Protocols](02-aliased-filesystem-registrations.md)

## Purpose And Review Status

Add Azure Blob Storage and ADLS Gen2 file discovery and reads through
`quackframe.register_filesystem`, using the existing
`AzureConnectionStringCredentials` and `AzureManagedIdentityCredentials` Blocks.
Both authentication strategies must coexist with each other and SFTP in one
shared DuckDB session, selected through independent named protocols.

Scope requested and implementation authorised on 2026-10-01. The user confirmed
that the two strategies belong in the existing models file and registry.

## Existing Repository Contract

- The filesystem registry currently contains only `sftp: SftpFilesystem`.
- The two Azure shared credential models already own validation and permit only
  `scope` overrides. Both require a scope after stored values and overrides merge.
- The connection-string Block contains `connection_string` and optional `scope`.
  The managed-identity Block contains `account_name`, optional `client_id` and
  optional `scope`.
- Both Blocks implement `to_credentials(model_type)` and can construct a new
  strategy that inherits their corresponding shared credential model. They
  already serve the Azure strategies for `register_secret`.
- `PrefectCredentialProvider.resolve(reference, model_type)` returns the concrete
  requested strategy. The shared loader applies its immutable overrides.
- `ProtocolFileSystem` translates paths and discovery results; `SessionResources`
  owns registration lifetime and cleanup. Neither requires a new Azure-specific
  runner or provider dispatch path.

The change adds filesystem strategies, not new credential providers or duplicate
Prefect Block definitions. Direct execution remains first-class; using the Prefect
credential provider does not require the Prefect runtime adapter.

## SQL Contract

Keep the existing signature and argument ordering:

```text
register_filesystem(provider, reference, filesystem_type, protocol = NULL, overrides = NULL)
```

Add these explicit registry entries:

| Filesystem type | Concrete strategy | Existing credential type |
| --- | --- | --- |
| `azure_connection_string` | `AzureConnectionStringFilesystem` | `azure_connection_string` |
| `azure_managed_identity` | `AzureManagedIdentityFilesystem` | `azure_managed_identity` |

Using separate type names makes authentication selection explicit and matches
the existing `register_secret` vocabulary. Do not infer the credential type from
a Block or introduce an ambiguous `azure` strategy.

Registration returns `true` on successful construction and publication. It does
not promise that credentials have been authenticated or every object is readable;
backends may authenticate on the first operation. Discovery and read failures
remain fail-fast. No eager container listing is required merely to register.

The default protocol remains the credential reference. Explicit protocols,
collision checks, positional/named arguments, and NULL/empty override semantics
remain unchanged. Standard Azure schemes remain reserved.

These proposed examples are independent alternatives. The Blocks select storage
account `examplestorage` and scope `az://reports/`:

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'azure-reports-key', 'azure_connection_string'
);
SELECT * FROM read_parquet(
    'azure-reports-key://examplestorage/reports/daily/*.parquet'
);
```

```sql
SELECT quackframe.register_filesystem(
    provider := 'prefect',
    reference := 'azure-reports-identity',
    filesystem_type := 'azure_managed_identity',
    protocol := 'reports-mi',
    overrides := MAP {'scope': 'az://reports/'}
);
SELECT * FROM read_csv('reports-mi://examplestorage/reports/daily/*.csv');
```

The second registration is equivalently expressed positionally as
`register_filesystem('prefect', 'azure-reports-identity', 'azure_managed_identity',
'reports-mi', MAP {'scope': 'az://reports/'})` and reads through the same
`reports-mi://` protocol. SQL contains credential references and paths only.

## Backend And Authentication

Use `adlfs.AzureBlobFileSystem` for both strategies, behind lazy optional imports.
The upstream project supports Blob Storage and ADLS Gen2 through the Blob API;
this phase targets file operations, not Data Lake administration or ADLS Gen1.
See the [adlfs project](https://github.com/fsspec/adlfs) and
[backend documentation](https://fsspec.github.io/adlfs/).

Connection-string strategy:

- Construct the backend with the resolved connection string explicitly.
- Derive the account identity used for path validation from the configured
  connection, without exposing the string or authentication components.
- Initially support Azure public-cloud HTTPS connections that identify an
  account. Validate the supported connection-string forms before publication;
  do not silently accept an endpoint configuration outside the agreed boundary.

Managed-identity strategy:

- Construct an explicit asynchronous `ManagedIdentityCredential` and pass it to
  the backend with the resolved `account_name` and anonymous access disabled.
- Omitted `client_id` selects the system-assigned identity; a supplied value
  selects a user-assigned identity. The identity SDK owns token acquisition and
  refresh. See Microsoft's
  [ManagedIdentityCredential contract](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.managedidentitycredential?view=azure-python).
- Do not substitute `DefaultAzureCredential`, CLI credentials, environment
  credentials, anonymous access or a different identity when authentication fails.
- Workload identity federation is a separate authentication mode and is outside
  this phase; a managed identity name alone does not imply support for it.

For both strategies, explicitly prevent ambient adlfs environment settings from
overriding the selected authentication or endpoint. Verify the selected dependency
version's precedence with tests; constructor arguments alone are not evidence of
isolation. SQL may override only `scope`, never the connection string, account,
client ID, token or backend options.

## Scope And Path Semantics

Read shape:

```text
protocol://account/container/absolute-blob-name
```

The protocol selects one backend. The authority is an account name, not an
arbitrary hostname; it must match the account fixed by that registration. The
backend receives `container/absolute-blob-name`. It must never reinterpret a read
URL as instructions to connect to a different account or choose other credentials.

Accept these scope forms after the inherited validation and filesystem-specific
parsing:

- `az://container/prefix/` and `azure://container/prefix/`, with the account supplied
  by the credential.
- `abfss://container@account.dfs.core.windows.net/prefix/`, whose account must match
  the credential. Here `container@account` is Azure scope syntax, not read-URL
  authentication.

Scope identifies the intended storage location and must be valid, but does not
prepend a root, rewrite blob names or enforce a container/prefix access boundary.
Every read supplies its container and complete blob name. Other containers on the
same account may be read when Azure permissions allow it. This follows the named
filesystem phase's explicit-path approach; Azure permissions remain authoritative.
Document this distinction from native DuckDB secret scope matching prominently.

Reject malformed scopes, conflicting accounts, missing containers, embedded
authentication in read URLs, ports, query strings and fragments. Validate these
rules in the filesystem strategies; do not tighten the shared Azure validator in
a way that silently changes existing `register_secret` behaviour.

Preserve blob-name case and slash structure without local-filesystem path
normalisation. Decode URL escapes once. Encoded wildcard characters identify
literal names, while raw glob syntax selects objects. Discovery results,
`info`/`ls` names and DuckDB filename metadata must retain the selected protocol,
account and container and be reusable in subsequent reads. Explicitly test names
containing spaces, percent signs, Unicode, `#`, `?` and literal wildcard characters.

## Ownership And Dependencies

Each registration constructs an independent uncached backend and owns any identity
credential and clients it creates. Preserve the existing owner lock, protocol
reservation, duplicate-handle rules and cleanup publication order.

The adlfs backend uses asynchronous Azure clients behind synchronous filesystem
operations. Establish how to close these clients and the identity credential on
their owning loop from the existing synchronous cleanup callback. Prove cleanup
on success, SQL failure, partial construction and failed registration. Do not
depend on garbage collection or shut down a shared fsspec event loop. Avoid
double-closing resources whose ownership is transferred to the backend.

Keep any necessary close/path helpers local to `register_filesystem`; preserve
the existing generic adapter unless evidence requires a small general correction.
No global cache, connection pool, transport patch or new retry layer is proposed.

Add a Poetry-managed `azure` extra containing compatible fsspec, adlfs and Azure
Identity dependencies, with directly imported packages declared explicitly. Select
and lock versions during implementation after checking supported Python versions
and the existing fsspec range. Document installation as `quackframe[prefect,azure]`
for a consumer using Prefect Blocks, and
`poetry install --extras "prefect azure"` in this repository.

Enabling a SQL function must not import the Azure backend eagerly. Missing backend
dependencies must name `quackframe[azure]`, rather than derive an extra from the
long filesystem type name. Review the existing registration function's fsspec
dependency error for this case. Core-only and SFTP-only environments must continue
to import and execute their supported paths without Azure packages installed.

## Boundaries

Included: Blob and ADLS Gen2 discovery, metadata, CSV/Parquet/blob reads, both
existing authentication models, multiple independent registrations, safe errors,
and deterministic cleanup across direct and optional Prefect runtimes.

The original exclusions below describe this read-focused phase.
[Filesystem Write Support](04-filesystem-write-support.md) now owns the approved
read/write contract and implementation for all strategies.

Excluded: new credential stores or Block fields; MSSQL filesystem access; writes,
deletes, copies and ACL administration; ADLS Gen1; Azure Files/SMB; arbitrary fsspec
options in SQL; custom endpoints, sovereign clouds and production emulator support.
A local emulator may support tests but cannot establish managed-identity or ADLS
Gen2 compatibility. Connection strings remain opaque secrets: this phase does not
introduce a separate SAS-token SQL option.

## Delivery And Acceptance

1. Review the proposed SQL names, account-bearing read URLs, scope semantics and
   public-cloud boundary before implementation. Resolve any changes in this file.
2. Verify backend authentication precedence, supported connection-string forms,
   path handling and asynchronous cleanup against the selected dependency versions.
   Record findings and exact versions here before committing to adapter details.
3. Implement the two strategies and explicit registry entries, reusing the shared
   models, provider and session owner. Add the optional extra and Poetry lock changes.
4. Update developer filesystem/credential docs and runnable examples alongside
   implementation, including prerequisites and direct-runtime usage.
5. Run the acceptance checks below and record results before marking Complete.

Acceptance checklist:

- [x] Existing Azure Blocks return the requested concrete filesystem subclasses;
      the same Blocks still support existing secret registration unchanged.
- [x] Both strategies validate required fields and scope overrides before backend
      creation; authentication fields cannot be overridden through SQL.
- [x] Explicit, default, positional, named and mixed protocol calls work; malformed
      protocols and duplicate/reserved registrations preserve existing resources.
- [ ] Two Azure registrations with distinct credentials/accounts, both Azure types
      together, and Azure plus SFTP remain independent in one session.
- [x] Host/account mismatches and hostile URL forms cannot redirect the backend;
      ambient settings cannot change the selected authentication.
- [x] Glob-to-read round trips, metadata and CSV/Parquet reads retain protocol and
      account identity across ordered SQL files, including special blob names.
- [ ] Missing objects, denied access and authentication failure produce safe errors
      without connection strings, keys, SAS tokens, access tokens or returned data
      in messages, exception chains or logs. Include deferred file-read failures.
- [x] Cleanup works after successful runs and all failure stages while the process
      remains alive; one registration's cleanup does not invalidate another.
- [x] Focused unit tests cover mapping and failures; real DuckDB integration tests
      exercise registration, discovery, reads and one/four-thread execution.
- [ ] Live Azure validation covers connection-string reads and system-assigned and
      user-assigned identities, with Blob and ADLS Gen2 accounts represented. Record
      unavailable infrastructure as a validation gap; mocks/emulators are not proof
      of live authentication. Do not provision infrastructure as an implicit step.
- [ ] Existing SFTP, credential-loading and secret-registration regressions pass.
- [ ] Full applicable checks pass: `poetry run pytest`, `poetry run ruff check .`,
      `poetry run pyright`, the documentation link checker and `git diff --check`.

## Implementation Evidence (2026-10-01)

The two concrete strategies and registry entries are implemented in
`src/quackframe/sql_functions/register_filesystem/models.py`. Backend-specific
helpers live in the lazily imported `azure.py` beside it. Existing Blocks,
credential loading and session ownership remain unchanged. The dependency error
now uses each strategy's explicit `extra_dependency_bundle`: `sftp` for SFTP and
`azure` for both Azure types. The base declares the field without a default;
there is no fallback to the filesystem type name. This consistency change was
requested on 2026-10-01.

Verified dependencies: adlfs 2026.8.0, Azure Identity 1.25.3 and Azure Storage Blob
12.31.0, with fsspec 2026.7.0 and DuckDB 1.5.5. The Poetry lock records exact
versions. adlfs 2026.8 is the minimum for this implementation.

Source inspection found that adlfs loads ambient storage settings and prioritises
an environment connection string even when an explicit token credential exists.
A small backend subclass therefore attaches an already constructed SDK client in
`do_connect`, clearing ambient credential fields before any backend connection is
selected. No process environment mutation is needed. An explicit construction
marker prevents upstream default-credential creation; it is never used as an
actual connection string. A managed identity is passed only to the owned SDK
client. Its transport closes with that client on the fsspec loop, idempotently,
including when upstream finalization later calls close again.

The backend also preserves already-decoded blob paths rather than interpreting
literal `#` or `?versionid=` as URL syntax. A reader wrapper sanitizes deferred
download errors. Parquet integration exposed the generic adapter's SFTP-only
`mtime` assumption; it now falls back to the backend's `modified()` method.

The Azure test module contains **55 tests**. It covers both authentication
constructors, ambient isolation, supported/rejected locations, special filenames,
independent accounts, partial construction cleanup, existing Block conversion,
real DuckDB/adlfs CSV/Parquet/blob reads with one and four threads, and ordered
SQL success/failure cleanup. Remote metadata and downloads are simulated; these
tests do not prove Azure authentication, network access or service permissions.
Fresh-process dependency tests also verify actionable `quackframe[azure]` errors
when fsspec, adlfs or Azure libraries are unavailable.

Azure Identity 1.25.3 can select workload federation from environment variables
even through `ManagedIdentityCredential`. Construction explicitly disables that
branch using the SDK's `_exclude_workload_identity_credential` option, with a
regression covering a populated workload environment. This version-sensitive
SDK option and the adlfs connection hook require revalidation on upgrades.

Validation results:

- Final Azure and shared credential-loading run: **68 passed**, including all
  **55 Azure tests** and fresh-process optional-dependency checks.
- Full suite at the first regression checkpoint: **310 passed, 4 failed**. All
  four failures are 60-second timeouts in `test_layer_diagnostics` for raw
  four-thread Paramiko/fsspec, with and without tracing. Those library controls
  bypass Quackframe's serialized SFTP implementation. Registered SFTP, fingerprint,
  turn-taking and lifecycle regressions passed. Five additional Azure tests were
  added after that full-suite collection and are covered by the final focused run.
- `poetry run ruff check src tests`: passed. The repository-wide command reports
  13 existing issues in the untouched `MAD.Utilities.DuckDB` prototype.
- Pyright, local Markdown links and `git diff --check`: passed.
- `poetry check --lock`: passed, with the existing license-table deprecation warning.

Live Blob/ADLS Gen2 and system/user-assigned identity validation remains pending.
The phase stays **In Progress** until outstanding acceptance evidence is recorded.

### Restoration Check

Restoration verified on 2026-10-01: the working tree was found with the original
SFTP-only `models.py`. Both Azure classes and registry entries, the base
`extra_dependency_bundle` declaration, and explicit SFTP/Azure bundle values were
restored. Finalizer type annotations were also restored. The resulting working
tree passed 130 focused tests, Pyright, source/test Ruff, Markdown links and
`git diff --check`. Full-suite and live Azure checks were not repeated.

## Related Docs

- [Filesystems](../../filesystems.md): current user-facing registration contract.
- [Credential Providers](../../credential-providers.md): shared models and Block conversion.
- [Named Protocols](02-aliased-filesystem-registrations.md): isolation and lifecycle rules.
- [Execution Lifecycle](../../execution-lifecycle.md): session ownership and cleanup.
- [Filesystem Examples](../../../examples/filesystems/README.md): runnable examples to extend.
