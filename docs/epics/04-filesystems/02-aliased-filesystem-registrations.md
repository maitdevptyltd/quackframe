# Named Filesystem Protocol Registrations

Status: **Complete**
Last updated: 2026-10-01
Epic: 04 Filesystems
Phase: 02
Related docs: [Filesystems](../../filesystems.md), [Execution Lifecycle](../../execution-lifecycle.md)

## Purpose And Review Status

Support multiple independently configured filesystems in one DuckDB session,
including multiple instances of the same filesystem type. Each registration
exposes its own protocol, so every read explicitly selects its backend.

Implementation authorised by the user on 2026-10-01. The user selected `protocol` as the argument name on 2026-10-01, with a
default derived from the credential reference. Examples must demonstrate both
positional and named arguments and state that they are equivalent. The user authorised implementation of this scope, including the collision,
lifecycle and migration decisions below.

## Baseline Before This Phase

- `register_filesystem(provider, reference, filesystem_type, overrides := NULL)`
  supports SFTP through an explicit strategy registry and shared credential loader.
- SFTP registers the standard `sftp` and `ssh` protocols. Another SFTP
  registration collides, even if its endpoint or credentials differ.
- The configured scope selects the host. Its directory is neither a path prefix
  nor an access restriction. Read URL authorities are stripped by the backend;
  changing the hostname in a read does not select another connection.
- A short-lived duplicate connection performs registration. The backend remains
  available to later ordered SQL files in the shared DuckDB instance.
- Failed registration closes the newly created clients. Successful registration
  has no explicit Quackframe finalizer; existing loopback evidence shows that
  closing DuckDB can leave an SSH transport active.

## SQL Contract

The argument order is:

```text
register_filesystem(provider, reference, filesystem_type, protocol = NULL, overrides = NULL)
```

`protocol` is the optional fourth argument; `overrides` moves to fifth.
When omitted, use the credential reference verbatim if it is a valid protocol
name. An explicit protocol allows the same reference to be registered more than
once with independently resolved configuration.

Every example must show the resulting protocol and a read using it. Positional
and named arguments are equally supported; named arguments are not mandatory.
The following snippets are independent alternatives, each starting in a fresh
session. Unless overridden, their credential references configure
`files.example.test` as the SFTP endpoint.

Omitting `protocol` uses the reference: `supplier-nz-files://`.

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-nz-files', 'sftp'
);

SELECT * FROM read_csv('supplier-nz-files://files.example.test/reports/daily-*.csv');
```

An explicit fourth positional argument selects `supplier-au://`.

```sql
-- Positional form.
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-au-files', 'sftp', 'supplier-au'
);

SELECT * FROM read_csv('supplier-au://files.example.test/reports/daily-*.csv');
```

Named arguments produce exactly the same `supplier-au://` registration and read.
This is equivalent to the preceding snippet; do not execute both in one session.

```sql
-- Equivalent named form.
SELECT quackframe.register_filesystem(
    provider := 'prefect',
    reference := 'supplier-au-files',
    filesystem_type := 'sftp',
    protocol := 'supplier-au'
);

SELECT * FROM read_csv('supplier-au://files.example.test/reports/daily-*.csv');
```

An override changes the endpoint to `alternate.example.test`; the explicitly
selected protocol remains `supplier-au://`. This example uses positional arguments
throughout, including the fifth-argument override map.

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-au-files', 'sftp', 'supplier-au',
    MAP {'scope': 'sftp://alternate.example.test/'}
);

SELECT * FROM read_csv('supplier-au://alternate.example.test/reports/daily-*.csv');
```

Mixing positional and named arguments can retain the default
`supplier-au-files://` protocol while supplying an override without a NULL
placeholder for the fourth argument.

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-au-files', 'sftp',
    overrides := MAP {'scope': 'sftp://alternate.example.test/'}
);

SELECT * FROM read_csv('supplier-au-files://alternate.example.test/reports/daily-*.csv');
```

For a variable-based workflow, the same default `supplier-nz-files://` protocol
can be prepended to a host-and-path glob. Discovery must return paths retaining
that protocol so the subsequent read selects the same registration.

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-nz-files', 'sftp'
);

SET VARIABLE source_glob = 'files.example.test/reports/daily-*.csv';
SET VARIABLE smart_path = concat(
    'supplier-nz-files://', getvariable('source_glob')
);

SELECT * FROM glob(getvariable('smart_path'));
SELECT * FROM read_csv(getvariable('smart_path'));
```

The return value remains `true` on success; errors fail the statement. Registration
is a separate setup statement, completed before discovery or reads.

Use `protocol` because the value defines the URI scheme used in reads.
Validate it as a URI scheme, not a SQL identifier. Protocol grammar:
`[a-z][a-z0-9+.-]*`. Hyphens remain intact; underscores and uppercase names
require an explicit valid protocol rather than silent rewriting.
`register_secret` remains unchanged: its `alias` names a DuckDB secret and its
default replaces hyphens with underscores for SQL identifier use. Do not add an
`alias` synonym to the filesystem API.

## Selection And Paths

The intended SFTP shape is `protocol://host/absolute/remote/path`:

| Component | Meaning |
| --- | --- |
| Protocol | Selects exactly one registered filesystem instance |
| Host and optional port | Must agree with that instance's configured endpoint |
| Path | Absolute path on the selected server; supports backend glob patterns |

Two protocols may use the same host and path with different credentials. A read
must never switch credentials or create another connection from its hostname.
Reject mismatched authorities rather than silently ignoring them. Compare parsed
hostnames and effective ports; an omitted port uses the registration's configured
port. Reject embedded authentication, query strings and fragments for SFTP.

Preserve current SFTP scope-directory semantics: do not implicitly prepend the
scope's directory. Directory rooting would be a separate public behaviour change.

Discovery must return reusable protocol-qualified paths. In particular,
`glob -> selected_paths -> read_blob` must retain the selected registration at
every step. Returned `filename` metadata must retain the protocol and endpoint too.
This supports workflows that discover files, filter dates, retain original bytes,
and then parse retained copies without accidentally selecting another account.

## Registration Architecture

Expose each protocol through a small fsspec adapter registered with DuckDB's existing
filesystem API. The adapter translates protocol URLs and delegates to its one owned
backend. It must cover discovery, metadata, opening and returned path translation;
changing only a backend's `protocol` attribute is not sufficient evidence that
all those paths work.

Keep these responsibilities separate:

- Shared credential loading resolves one provider reference and immutable,
  allowlisted overrides per registration.
- Each filesystem strategy owns typed configuration, endpoint validation,
  backend construction, path interpretation and resource cleanup.
- Registration owns protocol validation, collision checks and publication to DuckDB.
- A generic session resource owner provides deterministic cleanup without
  teaching the runner or function registrar about SFTP or Prefect.

Keep filesystem types explicitly allowlisted and optional dependencies lazy.
The design must accommodate different types and endpoints without assuming all
backends use SSH hosts or credentials. Each future type defines its own URL
authority/path mapping and authentication requirements. New production S3, Azure
or other strategies are outside this phase; use another test strategy to prove
the general registration boundary.

The reference [MAD.Prefect implementation](https://github.com/maitdevptyltd/MAD.Prefect/blob/main/mad_prefect/duckdb.py)
uses `MadFileSystem(DirFileSystem)` with fixed protocol `mad`, a configured
`basepath`, and a cached singleton. It demonstrates a custom protocol wrapper,
but this proposal does not inherit its directory rooting, global singleton or
object-ID registration tracking. Those differ from independent session-owned
registrations and the requested host-bearing paths.

## Collisions And Failure

- Protocol uniqueness spans all filesystem types within the shared DuckDB instance.
  Duplicate protocols fail, even when the supplied configuration appears identical.
- Reject protocols that conflict with native/backend protocols or externally
  registered primary filesystem names. Known fsspec schemes and an explicit
  native-scheme set are reserved even when not currently installed. See the
  external secondary-protocol boundary below.
- Reserve a protocol before loading credentials or connecting; publish only after
  successful construction and registration. Roll back the reservation and close
  partial resources on every failure. Preserve existing registrations.
- Protect registry mutation against concurrent attempts, without holding its
  lock over ordinary filesystem reads. Never silently replace another backend.
- Treat registration as session state, not transactional SQL data. SQL rollback
  does not promise to undo registration. No credentials are persisted in DuckDB.
- Keep errors actionable and free of credentials, key paths and raw backend
  diagnostics. Protocols and read URLs must not contain secrets.

## Lifecycle And SFTP Invariants

Each registration owns an independent backend and its cleanup operation. Retain
`skip_instance_cache=True`; do not pool or share clients between protocols.
Duplicate DuckDB handles must share the same registration lifetime, not own
independent registries that disappear when the duplicate closes.

This phase includes deterministic cleanup. After queries and their
file handles finish, release DuckDB handles and explicitly close all owned
backend resources on success, SQL failure and setup failure. Attempt every
cleanup and preserve the primary execution error. Cleanup failures must be
reported safely rather than silently treated as successful teardown.

`SessionResources(connection)` is the generic resource owner and binding context.
Caller-owned Python connections supply it explicitly and keep the root open
until all registered resources are released. Duplicate handles share that owner;
its root connection supplies the registration duplicates, avoiding DuckDB's
parent/child invalidation of nested duplicates. There is no process-global
connection-ID registry or reliance on garbage collection. Session-local
registrations are recreated on each run, including persistent database runs.

Preserve the existing SFTP adapter unchanged in substance:

- Verify configured SHA256 fingerprints before authentication and on reconnect.
- Reject malformed or mismatched fingerprints. Preserve absent/blank behaviour.
- Keep fingerprints and authentication fields unavailable to SQL overrides.
- Retain per-client synchronous request/response locking and synchronous directory
  listing through the same lock. Separate registrations have separate locks.
- Do not introduce global Paramiko patches, connection pools, automatic retries,
  or new guarantees for asynchronous prefetch, pipelined writes or network deadlines.

## Compatibility Decision

Named protocols replace standard-protocol filesystem registration
for this pre-release API. Existing three-argument calls still parse, but now expose
the reference as their protocol. Existing `sftp://...` reads must migrate to
`reference://...` or an explicit protocol. Existing fourth-position override maps
must move to fifth position, with a protocol or NULL in fourth position, or use
`overrides := MAP {...}`. Named `overrides` calls remain valid. Invalid default
protocol names require an explicit protocol. Do not add a compatibility overload
that guesses whether the fourth argument is a protocol or an override map.

This pre-release behaviour change was approved with implementation. Do not silently
assign the first registered filesystem as the owner of bare `sftp://` URLs.
Retaining standard protocols would require an explicit new mode, rather than
an implicit fallback.

## Delivery And Acceptance

1. Agreed protocol grammar, host-bearing paths, standard-protocol migration
   and deterministic cleanup scope; implementation authorised.
2. Specify the generic session ownership boundary and per-type adapter contract.
3. Implement registration, path translation and cleanup; update developer docs
   and runnable examples together.
4. Validate the outcomes below before marking this phase complete.

Acceptance outcomes (execution results are recorded below):

- Two SFTP protocols with different endpoints, and two credentials on the same
  endpoint, read the intended distinct content in one session.
- An additional test filesystem type coexists without runner/provider special cases.
- Protocol-preserving glob results can be passed to `read_blob` and `read_csv`,
  including later ordered SQL files, and retain protocol-qualified filenames.
- Unknown protocols, conflicting protocols, duplicate registrations and endpoint
  mismatches fail without altering existing registrations or leaking resources.
- Equivalent positional, named and mixed calls, default and explicit protocols,
  invalid scheme names, NULL/empty override maps,
  provider load failures and missing optional dependencies behave as specified.
- Existing fingerprint and one/four-thread SFTP regressions continue to pass.
- Successful, failed and partially constructed runs leave no owned SSH transport
  active; persistent workers and duplicate handles obey the agreed lifetime.
- Run relevant focused tests, full applicable repository checks, documentation
  links and `git diff --check` after implementation is authorised.

## Related Docs

- [Previous Filesystem Phase](01-shared-credential-loading-and-fsspec.md): existing
  fingerprint, concurrency and unresolved lifetime evidence.
- [Filesystems](../../filesystems.md): current public behaviour and migration guidance.
- [Credential Providers](../../credential-providers.md): shared loading and overrides.
- [SQL Function Extensions](../../python-extensions.md): neutral installation and binding.
- [Execution Lifecycle](../../execution-lifecycle.md): session ownership and failure.

## Implementation Direction

A generic `SessionResources(connection)` context owns the root connection
reference, cleanup callbacks and the resource-registration lock. Resource-aware
function descriptors bind this owner outside the SQL signature. The engine
supplies it; callers installing
resource-aware functions on their own connections must supply an explicit owner
and finish all reads/duplicate-handle work before leaving its context. Each
registration retains a root-derived duplicate handle for unregistering during
cleanup, then
closes its backend and that handle before root connection closure and temporary
database deletion. DuckDB closes nested duplicates with their parent, so the
root owner must outlive all registrations; child handles never own this lifetime.
No process-global connection registry is used.

Protocol validation reserves known fsspec schemes and DuckDB native schemes, then
checks DuckDB for existing registrations. DuckDB remains the final collision
arbiter for primary names, with the conservative external-wrapper rule below.

### External Protocol Boundary

DuckDB 1.5.5 exposes only an external filesystem's primary name through
`list_filesystems()` and `filesystem_is_registered()`. A probe with an external
`("custom-a", "custom-b")` wrapper confirmed that `custom-b` is invisible to
those checks and can be registered again. Known native/fsspec schemes and
external primary names are rejected. Because arbitrary external secondary
schemes cannot be discovered reliably, registration also rejects any existing
external Python filesystem not registered through the shared resource owner.
This conservative boundary prevents ambiguous routing. All Quackframe wrappers
expose exactly one scheme and share that owner, so independent registrations
coexist. Native DuckDB readers remain available. Do not mutate managed
registrations through external registration APIs.

## Verification (2026-10-01)

Implemented named protocol registration, bidirectional path translation,
independent backends and deterministic cleanup. Updated public docs and examples.
The existing fingerprint and synchronous exchange-lock implementation is preserved.

- Full suite: **243 passed, 4 failed**. The failures are the existing raw upstream
  four-thread Paramiko/fsspec diagnostics (traced and untraced), which time out
  without the production serialization adapter. All Quackframe production and
  Prefect tests in that run passed. This run preceded the final conservative
  external-wrapper collision guard.
- Final core rerun after that guard: **177 passed** using
  `poetry run pytest --ignore=tests/test_prefect_integration.py
  --ignore=tests/test_sftp_integration.py -q
  --basetemp=.quackframe/protocol-core-final -p no:cacheprovider`.
- Final production SFTP rerun: **21 passed, 30 deselected**, covering discovery,
  one/four-thread reads, repeated serialized reads, host-key checks before
  authentication, runtime cleanup on success/failure, and two endpoints plus a
  second filesystem type in one session. Command:
  `poetry run pytest tests/test_sftp_integration.py -k "registered_sftp or
  runtime_closes or two_endpoints or fingerprint or csv_counts or discovery"
  -q --basetemp=.quackframe/protocol-sftp-final -p no:cacheprovider`.
- Same-host credential isolation is covered with distinguishable mocked SFTP
  backends. Different endpoints, ports, keys and pinned fingerprints are covered
  with real loopback servers. External production-server verification was not run.
- `poetry run pyright`: **0 errors, 0 warnings**.
- `poetry run ruff check src tests`: **passed**. Repository-wide
  `poetry run ruff check .` still reports **13 existing findings** under the
  untouched `MAD.Utilities.DuckDB` prototype.
- Documentation links and `git diff --check`: **passed**.

Windows sandbox restrictions prevented pytest temporary-directory access and
Pyright interpreter discovery. Successful test/type-check runs used approved
execution outside the sandbox; tests retained their artifacts under `.quackframe/`.
No dependency changes, commits, external deployments or production credentials
were involved.


### Review Follow-Up (2026-10-01)

SFTP discovery now percent-encodes returned paths and reads decode them once.
Encoded wildcard characters remain literal during backend glob expansion, so
special filenames round-trip through discovery, `read_blob` and `read_csv`
without selecting neighbouring files. Raw SQL glob operators remain supported.
Optional test imports and dependency guards keep core collection independent of
SFTP extras; memory-backend tests still run when only Paramiko is absent.
Fingerprint verification and synchronous SFTP locking are unchanged.

- Core suite: **186 passed**, excluding Prefect and SFTP integration modules.
- Focused SFTP/Prefect integration: **22 passed, 50 deselected**, with one
  loopback-server teardown connection-reset error in the mismatched-fingerprint
  case. All three fingerprint registration cases passed on immediate rerun.
- Full collection with Prefect, fsspec and Paramiko blocked: **173 collected**;
  with only Paramiko blocked: **194 collected**. Prefect itself requires fsspec,
  so the core-only collection check excludes that optional integration too.
- Regression subprocesses separately block fsspec and Paramiko while running
  filesystem tests, asserting that core tests run and backend tests skip.
- Ruff on `src`/`tests`, Pyright, documentation links and unstaged whitespace
  checks passed. Full upstream concurrency diagnostics were not rerun.
- No commits or staging; the existing index was verified unchanged.
