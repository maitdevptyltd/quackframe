# Shared Credential Loading And fsspec Filesystems

Status: **In Progress**
Last updated: 2026-10-06
Epic: 04 Filesystems
Phase: 01
Related docs: [Credential Providers](../../credential-providers.md), [SQL Function Extensions](../../python-extensions.md)

## Outcome And Authority

The [named-protocol phase](02-aliased-filesystem-registrations.md) supersedes this
phase's standard-protocol SQL registration and unresolved managed-session cleanup.
Its explicit resource owner closes registered clients on success and failure.
The earlier investigation below remains historical evidence; fingerprint and
synchronous exchange-serialization behaviour are preserved. External-server
verification and network deadline policy remain separate concerns.

Accepted addition (2026-09-30): the SSH Block and shared credential model gain
optional `host_key_fingerprint: str | None = None`. SFTP verifies a supplied
OpenSSH SHA256 fingerprint before authentication; absent or blank values retain
automatic acceptance. Malformed or mismatched values fail registration. SSHFS
secret registration warns when a nonblank fingerprint is supplied but keeps its
SQL and parameters unchanged. SQL cannot override the fingerprint. This addition
is implemented and verified: 157 core tests, 14 Prefect provider/Block tests and
eight loopback fingerprint/discovery/CSV tests passed. The mismatch case confirms
zero authentication attempts. Ruff, Pyright, documentation links and whitespace
checks passed. The phase remains In Progress for the existing deployment/lifetime
gaps; no production server or Prefect server was used for this addition.

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

## Loopback CSV Hang Investigation (2026-09-28)

Status remains **In Progress**. The new local evidence exposes a concurrency
failure and a separate resource-lifetime failure in the accepted standard
backend. Production source is unchanged; transport/lifecycle redesign has not
been approved or implemented.

### Reproduction And Results

Tested branch commit: `ea42c8816918ea048d7cfa522d86aad35399018f`.
Inspected older branch: `feat/fsspec-sftp` at
`5009a5190a8e071d14cd084f644d1251df7281f8`.

Environment: Windows, CPython 3.13.9, Quackframe 0.1.0, DuckDB 1.5.5,
fsspec 2026.7.0, Paramiko 4.0.0, Pydantic 2.13.5, pytest 9.1.1.
Dependencies were installed from the existing Poetry lock with the `sftp` extra.

The [integration tests](../../../tests/test_sftp_integration.py) start a real
Paramiko SFTP server on `127.0.0.1` and an ephemeral non-default port. Both SSH
keys and all files are generated locally. There are 26 daily CSVs, with
`8192 + day` rows per file (213,343 total), over 1 MB each, alternating column
order and an extra column on odd days. A nonmatching file checks glob filtering.

The [child probe](../../../tests/sftp_probe.py) registers a test credential
provider through the existing registry. It returns the requested concrete model
with temporary local credentials and original scope `sshfs://127.0.0.1`.
SQL overrides that scope to `sftp://127.0.0.1`. Shared validation, overrides,
`quackframe.register_filesystem`, the direct runtime, DuckDB, fsspec, Paramiko,
and the SFTP transport all remain real. A child import guard prohibits Prefect;
no Prefect server or external service credentials are involved.

Discovery runs independently. Read cases first execute the reported SELECT
with the local endpoint, then repeat it into a persistent temporary result table
for exact Python assertions, because `run()` intentionally does not return query
rows. Every expected filename and count is checked. DuckDB/fsspec reports
canonical filenames as `sftp:///from_test/trips/...`, omitting the URL authority.
The provider is called once and the original credential scope stays unchanged.

| Case | Result |
| --- | --- |
| Independent glob, four threads | Pass: exactly 26 expected paths |
| Single CSV, one and four threads | Pass: exactly 8,193 rows |
| Wildcard, one thread | Pass: all 26 exact per-file counts |
| Wildcard, four threads | Hangs; child killed at the 60-second deadline |
| Session cleanup after successful read | Fails: one SSH transport still active after session close and GC |
| Session cleanup after real missing-file read failure | Fails: one SSH transport still active; later SQL does not execute |
| Deliberately stalled server read | Pass: watchdog captures blocked read stacks; parent kills and reaps child |
| Harness cleanup | Pass: client disconnects after exit/kill; server transports, subsystem threads, listener and file handles are closed; private key removed |

The exact SELECT timed out in both confirmation runs; an earlier exploratory
CTAS form also timed out. The final matrix is **5 passed, 3 failed** in 79.68
seconds. The one-thread wildcard probe completed in 4.74 seconds, including
two complete executions, result verification and the 0.5-second cleanup
observation. The generated CSVs total 29,015,181 bytes on this Windows host.
All eight child runs disconnected after exit or forced termination; every
server fixture completed teardown without error.

Each ordinary child has a 60-second hard timeout and dumps all Python thread
stacks at 42 seconds. The deliberately stalled read uses a five-second deadline.
Logs, generated SQL, versions, results, and parent process/connection diagnostics
remain in pytest's temporary directory; generated private keys are removed in
fixture teardown. The new regressions deliberately fail for the unresolved
four-thread and runtime-cleanup defects rather than skipping or accepting them.

Run without a Prefect server:

```powershell
poetry run pytest tests/test_sftp_integration.py -v --tb=short
```

For retained artifacts under the ignored workspace directory (choose a fresh
basename; pytest clears an existing `--basetemp` directory):

```powershell
New-Item -ItemType Directory -Force .quackframe
poetry run pytest tests/test_sftp_integration.py -v --tb=short --basetemp=.quackframe/sftp-repro
```

### Interpretation And Proposed Scope Review

The four-thread timeout shows four execution threads simultaneously blocked in
`SFTPClient._read_response` / `_read_packet` / `Channel.recv`, reached through
fsspec `open` or `size`/Paramiko `stat`. The transport thread is waiting for SSH
packets. Registration and listing have succeeded. One-thread reading completes
in seconds with identical files and SQL options. This strongly supports a
shared synchronous SFTP-client concurrency problem; a stack dump alone does not
prove exactly which response was lost or consumed by another reader.

Inspection of installed fsspec shows one shared `ftp` client for opening,
metadata and file reads. Paramiko protects request-number bookkeeping, but its
synchronous `_request` does not serialize the complete send/receive exchange.
The old `SerializedSFTPClient` serialized that exchange and replaced pipelined
`listdir_iter`; its managed filesystem also added finalization and other SSH
policy. Its two tiny CSV tests lacked the new bounded-process coverage. Those
old changes are evidence, not an approved implementation to restore wholesale.

The ordinary fsspec SFTP class has no explicit close/finalizer implementation.
Closing the DuckDB session and running GC leaves an active Paramiko transport
in these probes. Process isolation cleans up the test, but does not solve the
lifetime of connections in a persistent runtime worker.

A caller-selected `SET threads = 1` is a locally verified reading mitigation.
It does not solve session cleanup and is not yet verified against the external
server or the Prefect runtime. Do not silently force global DuckDB settings.

**Proposed, not accepted:** review a narrowly scoped SFTP adapter that owns
serialization across complete request/response exchanges, including directory
iteration, and explicit idempotent cleanup tied to the owning database session
on success and failure. Preserve the shared loading/model/SQL contracts. Review
whether a supported upstream solution can supply these guarantees before
committing to private Paramiko hooks. A serial adapter would trade throughput
for correctness; any private hooks require pinned-version regression coverage.
Do not bring across unrelated SSH trust-policy, routing or pooling behavior.

This proposal crosses the explicit custom-transport and lifecycle exclusions
above and therefore requires scope approval. No small constructor-only fix has
been established. Before accepting a redesign, require repeated four-thread
passes with exact counts, cleanup before process exit on success/failure,
rejected-registration cleanup, and cancellation/timeout behavior. Local evidence
does not establish behavior under network latency or remote server limits.

### Repository Validation

- Existing non-Prefect tests: **139 passed**. The Prefect integration module
  was explicitly excluded because it starts a test Prefect server.
- New loopback matrix: **5 passed, 3 failed**, exposing the unresolved defects
  above; none of these regressions are marked expected-failure or skipped when
  the SFTP dependencies are installed.
- `poetry run ruff check src tests`: passed.
- `poetry run pyright --pythonpath .venv/Scripts/python.exe`: zero errors or warnings.
- Local Markdown link/anchor check and `git diff --check`: passed.
- Full `poetry run ruff check .`: 13 pre-existing findings under the unchanged
  `MAD.Utilities.DuckDB` prototype (unused suppressions, imports, nested context
  managers and enum style). No unrelated lint cleanup was performed.
- Production source, `pyproject.toml` and `poetry.lock` are unchanged. The
  pre-existing untracked `assquack/` directory is preserved.

### Remaining Deployment Validation

Verify the consuming environment's exact Python/DuckDB/fsspec/Paramiko versions,
repeat single-file and 26-file reads with `SET threads = 1`, then validate the
approved fix under four threads. Separately exercise Prefect Block loading and
the Prefect runtime, including repeated runs in one worker, cancellation and
Ctrl+C/Stop behavior. The loopback tests do not establish prompt interrupt
handling: they deliberately use an external hard kill for bounded cleanup.

No external SFTP, Prefect or Azure credentials were used. Nothing was committed
or pushed.

## Request/Response Diagnostics (2026-09-30)

The harness now isolates the concurrency failure below DuckDB and fsspec.
Production code and dependencies remain unchanged at the tested commit above.
This extends the investigation; it does not implement the proposed adapter.

### Added Evidence

[Packet tracing](../../../tests/sftp_trace.py) wraps the installed Paramiko
methods and always calls their original implementations. Client and server
JSONL records include monotonic timestamps, process/thread/native-thread IDs,
client/channel identity, operation, request/response ID, packet type/size,
requested byte count, and call completion or exception type. No arguments,
credentials, keys, file contents or packet bodies are logged. The only logging
lock covers a single line write, never a transport call or request exchange.

The existing child watchdog and external 60-second deadline remain in place.
The parent writes `trace-summary.json` even after a timeout or child exception.
It reconciles client sends, server receipts and replies, overlapping packet
readers, pending synchronous waiters, and replies consumed by another thread
whose intended waiter is still pending. Raw `client-trace.jsonl`,
`server-trace.jsonl`, `child.log`, settings, SQL and parent diagnostics remain
alongside that summary. Correlation assumes one connection per probe.

Layer controls perform real `stat`/`open`/full CSV reads over one shared client
through Paramiko alone, then fsspec alone, then the original Quackframe SQL path.
Every layer uses the same 26 synthetic files and checks the same exact counts.
The library-only controls explicitly close the clients they own; Quackframe
session cleanup is still assessed separately. Each layer runs with one and four
workers, both traced and untraced, to expose timing perturbation by the tracer.

| Layer | One worker, traced and untraced | Four workers, untraced | Four workers, traced |
| --- | --- | --- | --- |
| Paramiko only | Exact counts pass | 60-second timeout | 60-second timeout |
| fsspec only | Exact counts pass | 60-second timeout | 60-second timeout |
| Quackframe/DuckDB | Exact counts pass | 60-second timeout | `SFTPError: Garbage packet received` |

A separate traced Paramiko repeat also timed out. Its trace proves a concrete
response mix-up on a single client/channel:

- The reader waiting for request **8** consumed the `attrs` response for **6**.
- The reader waiting for request **6** consumed the `attrs` response for **8**.
- That same reader waiting for **6** consumed the `handle` response for **10**.
- The server trace confirms those exact response IDs, types and lengths were
  sent. The intended waiters for **6**, **8** and **10** remained pending at
  the deadline. No sent requests were missing from the server trace, and no
  server-received requests lacked a server response.

The fsspec-only trace independently shows response **1** consumed by the reader
waiting for **4**, while request **1** remains pending. These observations
establish that sharing this synchronous Paramiko client between concurrent
readers is sufficient to fail; neither DuckDB nor fsspec is required to trigger
it. The installed `_read_response` implementation removes the response's
expectation, returns only if its ID matches the current waiter, and does not
forward another synchronous caller's response. This explains the stranded
waiters. The additional `Garbage packet received` error is consistent with
concurrent consumption of the same framed byte stream; packet contents are not
captured, so the exact byte interleaving is not reconstructed.

An important diagnostic control: successful one-thread DuckDB runs drain queued
pipelined directory EOF replies while closing a directory handle. Those replies
can differ from the current waiter's ID without any fault. The analyzer therefore
does not classify a mismatched ID alone as a lost response. The first matrix run
exposed an overly strict diagnostic assertion for that healthy case; the
assertion was corrected, the one-thread DuckDB control rerun successfully, and
[focused tests](../../../tests/test_sftp_trace.py) now check this distinction and
payload exclusion. All six four-worker failures remain real backend failures.

### Running The Extended Diagnostics

```powershell
poetry run pytest tests/test_sftp_integration.py -k layer_diagnostics -v --tb=short
poetry run pytest tests/test_sftp_trace.py -v
```

`-k layer_diagnostics` selects the 12-case layer matrix. Add `and not untraced`
to select only traced runs; `traced` alone also matches the word `untraced`.
Expect roughly six minutes when all six concurrent cases hit their deadline.
Use a fresh `--basetemp` to retain artifacts as described above. Backend failures
remain failing tests; diagnostics do not convert failures into passes.

### Implications For A Fix

Protection must cover shared request/response and packet-reading ownership,
including metadata operations such as `stat` and `open`. A lock solely around
CSV parsing or file `read()` is insufficient for the observed metadata races.
The evidence supports reviewing serialization of the complete SFTP exchange or
independent clients/channels with explicit ownership. Either requires the scope
review already described; neither is implemented here. The local one-thread
mitigation still passes and the separate runtime connection-lifetime issue
remains unresolved.

Validation of the extension: the non-Prefect core and metadata-correlation
suite passed **142 tests**. The original eight-case integration matrix still
reports **5 passed, 3 failed**, unchanged in meaning. The corrected one-thread
traced DuckDB control and all three focused tracer tests passed together. Ruff
for `src`/`tests`, formatting of the four harness files, full Pyright, Markdown
links and diff checks passed. The pre-existing full-repository prototype lint
findings documented above were not changed.

All completed diagnostic children disconnected after exit/kill, server fixtures
closed without teardown errors, and temporary private keys were removed. No
Prefect server or external credentials were used. The test environment and
commit match the 2026-09-28 record. Nothing was committed or pushed.

## Test-Only Turn-Taking Candidate (2026-09-30)

The user authorized an integration-test proof before framework implementation
or production-server testing. [The candidate](../../../tests/sftp_turn_taking.py)
is confined to `tests/`; no production source, dependency or SQL contract changed.
The previously excluded production transport/lifecycle redesign remains separate.

The candidate uses one reentrant lock per SFTP client around the complete
synchronous `_request` exchange. A `finally` block releases it on errors.
`listdir_iter` uses standard synchronous `listdir_attr` operations through the
same lock instead of pipelined directory requests. Credentials, host-key policy,
network transport, DuckDB and fsspec remain real and unchanged. A child-process
factory hook selects the experimental client when requested; this global test
hook is not a proposed production installation mechanism.

### Proof Conditions

The [turn-taking tests](../../../tests/test_sftp_integration.py) cover:

- Five untraced and five traced fresh child processes, each executing the exact
  26-file wildcard SELECT with four DuckDB threads and repeating it into a table
  for exact filename/count assertions: 213,343 rows per execution.
- Counters that prove multiple actual reader threads and contended lock
  acquisitions. Passing does not mean DuckDB was reduced to one thread.
- Four-worker Paramiko-only and fsspec-only controls mixing directory discovery,
  full reads, deliberately missing-file requests and subsequent successful
  reads, with tracing both off and on.
- The real Quackframe failure path after reading a file: the missing-file error
  returns, later SQL remains unexecuted, and no synchronous waiter remains.
- A deliberately stalled server: stacks are captured and the parent kills and
  reaps the child at its five-second deadline. The lock does not itself provide
  a network timeout or make Ctrl+C responsive.
- Traced assertions of zero overlapping packet readers, zero stolen replies
  belonging to pending waiters, no unexplained mismatched responses, and no
  pending synchronous waiters after successful reads.

An initial diagnostic assertion rejected all out-of-order replies, although all
ten candidate CSV runs returned exact counts. Inspection showed these remaining
replies were STATUS acknowledgements for asynchronous file CLOSE requests from
Paramiko's file destructor, with no synchronous waiter. The classifier now
allows only server-confirmed CLOSE acknowledgements whose request had no waiter;
focused positive/negative tests ensure a CLOSE with a waiting caller is not
misclassified. The checks for overlapping readers and stranded synchronous
waiters remain, and raw traces are retained.

### Verified Results

The final focused run passed **21 tests** in 70.53 seconds: 16 real integration
cases and five diagnostic-classifier tests. All ten four-thread SQL repetitions
returned every expected filename/count, with four observed reader threads and
thousands of contended lock acquisitions per process. Traces showed no overlapping
packet readers, stolen pending replies or unexplained response mismatches.
Mixed discovery/read/error cases and the external timeout/cleanup check passed.

The unchanged control was rerun separately: one thread passed; four threads
still hung and was killed at 60 seconds. Thus the passing candidate did not
merely benefit from a changed workload or reduced DuckDB thread count.

The non-Prefect core and tracer suite passed **144 tests**. Source/test Ruff,
full Pyright, harness formatting, documentation links and diff checks passed.
Production source and dependency files remain unchanged at
`ea42c8816918ea048d7cfa522d86aad35399018f` with the same dependency versions
recorded above. No temporary private keys or probe children remain.

Run the focused proof without a Prefect server:

```powershell
poetry run pytest tests/test_sftp_integration.py -k turn_taking -v --tb=short
poetry run pytest tests/test_sftp_trace.py -v
```

### Adoption Boundary

Successful local proof establishes viability for the tested read-only CSV and
directory operations, on the pinned environment above. It does not establish
arbitrary Paramiko asynchronous prefetch/write usage, large-directory memory
behavior (the candidate materializes directory entries), remote latency/server
limits, production-server behavior, or prompt Ctrl+C handling.

Turn-taking does not repair the separate connection-lifetime defect. The direct
runtime still leaves one SSH transport alive after success or failure; the test
continues to record it without forcibly closing it inside the runtime. Child
exit/kill and fixture teardown clean up the harness. Library-only controls,
which explicitly own and close their clients, have no remaining transport.

Framework integration should select the implementation through the SFTP
strategy, preserve parallelism for unrelated backends, and address session
resource ownership before deployment. No production SFTP server was accessed.
Nothing was committed or pushed.

## Related Docs

- [Credential Providers](../../credential-providers.md): shared models and provider contracts.
- [Filesystems](../../filesystems.md): SQL usage, endpoint interpretation and ownership.
- [SQL Function Extensions](../../python-extensions.md): function-owned packages and registration.
- [Execution Lifecycle](../../execution-lifecycle.md): session ownership and ordered SQL.
- [Credential Function Example](../01-mvp/07-credential-function-example.md): original strategy implementation scope.

## Accepted SFTP Serialization Fix (2026-09-30)

The user authorised production adoption after the loopback proof. This supersedes
this phase's earlier exclusion of SFTP serialization only. `SftpFilesystem`
selects a small fsspec subclass with a per-client lock around each synchronous
Paramiko request/response exchange. Directory iteration uses synchronous listing
through the same lock. Authentication, credential loading, overrides, paths and
SQL remain unchanged. No global monkeypatch or connection pool is introduced.

The fix covers synchronous filesystem reads and listing. Arbitrary asynchronous
prefetch and pipelined writes are outside the verified contract. Persistent-worker
connection cleanup and network timeout policy remain separate unresolved work;
serialization does not bound a server that stops responding. Future pooling must
be justified by throughput measurements and separately designed and validated.

Production regression tests must exercise normal SQL registration without the
experimental SSH hook, with one and four DuckDB threads and repeated traced reads.

### Production Adoption Verification

Tested the uncommitted fix on `6a8dbf84ed8d5d7cee99bbc784e1b3349156696d`
in the consuming workspace's `quackframe` submodule. Python 3.13.9, DuckDB 1.5.5,
fsspec 2026.7.0, Paramiko 4.0.0, Pydantic 2.13.5 and pytest 9.1.1.

- Ten normal production-registration runs (five traced, five untraced), four
  DuckDB threads: all returned exactly 26 file counts / 213,343 rows. Each child
  completed in 3.04-5.26 seconds, including two CSV executions and cleanup probing.
  Traces had no overlapping packet readers, unexplained response mismatches,
  stranded responses or pending waiters. No test client substitution was enabled.
- Discovery, single-file and wildcard one/four-thread checks passed. Instrumented
  mixed listing/read/error controls, stalled-server stack capture and child cleanup
  passed. The normal production missing-file failure returned promptly as well.
- Core suite excluding Prefect-server and SFTP integration tests: 144 passed.
  Source/test Ruff and Pyright passed; documentation links and whitespace checked.
- The first combined run had one obsolete backend-selection unit expectation;
  it was updated and passed in the core suite. The loopback cases passed.
- Rechecked session lifetime: both success and failure still leave one active SSH
  transport until child exit. These two existing regression assertions remain red;
  raw unmodified-library concurrency diagnostics are also intentionally retained.
  No production server or Prefect runtime was used. Validate external-server
  counts and throughput using four threads and a bounded worker before deployment.

Artifacts: `.quackframe/sftp-production-verified/`,
`.quackframe/sftp-production-failure/`, `.quackframe/core-production-fix/`.

### Upstream Diagnostic Failure Classification (2026-10-06)

The unprotected four-thread Paramiko/fsspec controls can terminate with
`paramiko.sftp.SFTPError: Garbage packet received` instead of reaching their
known deadlock timeout. CI exposed that the parent rejected this child exit
before it could be classified as an expected upstream race.

The [probe](../../../tests/sftp_probe.py) now retains the exception type and
message in `error.json` while preserving its traceback and failing exit code.
The [parent harness](../../../tests/test_sftp_integration.py) accepts only that
exact exception for the unprotected four-thread `multi` library controls.
Protected clients, single-thread controls, other workloads, and unrelated
exceptions still fail. Timeout handling and production code are unchanged.

[Classification regressions](../../../tests/test_sftp_probe_result.py) cover
those boundaries and successful results. Local Windows/Python 3.13.9 validation
completed: the classification, SFTP integration and trace suites reported
**80 passed, 4 xfailed**. Pyright, scoped Ruff, changed-file formatting,
documentation links and whitespace checks passed. Repository-wide Ruff retains
13 pre-existing prototype findings. The full suite and hosted Python 3.11 matrix
were not rerun for this change. The diagnostic fix is complete; the phase remains
In Progress for its separate external-server verification concerns.
