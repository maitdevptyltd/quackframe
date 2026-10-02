# Filesystems

Register independently configured filesystems in one DuckDB session and select
one explicitly with its protocol in every path. SFTP and Azure Blob/ADLS Gen2
strategies each own their credentials, endpoint and connection.

## Reads, Writes And Access Control

Every registered strategy supports reads and writes: `sftp`,
`azure_connection_string` and `azure_managed_identity`. The person configuring
credentials and remote permissions controls access. Azure authorization rules
and the SFTP account's filesystem permissions and server restrictions remain
authoritative. There is no separate Quackframe write-enable option. Read-only
credentials can register and read; denied operations fail without exposing
backend credential details. Registration does not probe write permissions.

Use the same named protocol for DuckDB exports:

```sql
SELECT quackframe.register_filesystem('prefect', 'output-files', 'sftp');
COPY (SELECT 42 AS value)
TO 'output-files://files.example.test/exports/result.parquet' (FORMAT PARQUET);
```

Both Azure strategies accept the same `COPY ... TO` operations with paths such as
`output-blobs://reports/result.parquet`. Paths are explicit; scope
never prepends a destination root. Azure containers must already exist.
For a single SFTP file, its parent directory must already exist. Partitioned
exports create their required directories and accept nested output paths.

With DuckDB 1.5.5, a single-file export replaces an existing destination, using a
temporary file and move where DuckDB requires it. SFTP replacement uses the
server's POSIX rename extension. Azure replacement streams through the selected
client, waits for completion and then removes the temporary source; it is not an
atomic rename and may require read and delete permissions as well as write.

Partitioned CSV/Parquet exports support `PARTITION_BY`, `APPEND` and `OVERWRITE`.
`APPEND` adds new files; it does not append bytes to existing files. `OVERWRITE`
removes existing output under the selected destination before writing and thus
requires deletion permissions. An empty partitioned query produces no data files.
Use dedicated output directories and select export options deliberately.

Successful exports finish writing before later SQL files run. Failed exports
stop subsequent SQL files and can leave partial output or temporary files.
Quackframe provides neither remote rollback nor automatic retry. Inspect the
failure and destination before deciding how to recover; session cleanup releases
clients without deleting existing output as a recovery action.

Local tests exercise writable and read-only loopback SFTP, real DuckDB/adlfs
exports with controlled Azure service responses, multi-block uploads, append,
replacement, partition overwrite and upload failures. Live Azure Blob/ADLS Gen2
and deployed managed-identity writes still require environment validation; see
[write-support evidence](epics/04-filesystems/04-filesystem-write-support.md).

## Azure Blob And ADLS Gen2

The existing `AzureConnectionStringCredentials` and
`AzureManagedIdentityCredentials` Blocks also support filesystem registration.
Select `azure_connection_string` or `azure_managed_identity` as the filesystem
type. No new Block or credential provider is needed.

Install `quackframe[prefect,azure]` in a consuming project, or run
`poetry install --extras "prefect azure"` in this repository. Enable
`register_filesystem` in `[tool.quackframe.functions].enabled` as shown below.
The direct runtime works with these Prefect-backed credentials.

For a connection-string Block named `azure-reports-key`, with account
`examplestorage` and scope `az://reports/`:

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'azure-reports-key', 'azure_connection_string'
);
SELECT * FROM read_parquet(
    'azure-reports-key://reports/daily/*.parquet'
);
```

For a managed-identity Block named `azure-reports-identity`:

```sql
SELECT quackframe.register_filesystem(
    provider := 'prefect',
    reference := 'azure-reports-identity',
    filesystem_type := 'azure_managed_identity',
    protocol := 'reports-mi',
    overrides := MAP {'scope': 'az://reports/'}
);
SELECT * FROM read_csv('reports-mi://reports/daily/*.csv');
```

Positional and named forms are equivalent. For example, the second registration
can be written as `register_filesystem('prefect', 'azure-reports-identity',
'azure_managed_identity', 'reports-mi', MAP {'scope': 'az://reports/'})` and selects
the same `reports-mi://` paths.

Read and write paths use `protocol://container/blob-name`. The registration
selects the storage account from its connection string or configured
`account_name`; URLs never select or repeat the account. Every path includes the
container and complete blob name; scope never prepends a directory or restricts
access to a prefix. Other containers
on the account remain available when Azure permissions allow. Unlike native
DuckDB secret scope matching, scope does not select credentials for each read.

Scopes accept `az://container/prefix/`, `azure://container/prefix/`, or
`abfss://container@account.dfs.core.windows.net/prefix/`. A trailing slash is
required and any explicit account must match. Only scope can be overridden in
SQL. Filesystem URLs reject authentication, ports, query strings and fragments;
URL-encode literal special characters in blob names. Discovery returns reusable,
encoded protocol-qualified paths. Literal `=` remains visible so partition
directories such as `file_date=2026-09-16` can be extracted directly from
`read_csv` and `read_blob` filenames. Percent signs, URL delimiters and wildcard
characters remain escaped; a literal `%3D` in a blob name becomes `%253D`,
distinct from `=`. Reads decode paths once.

Replace older `protocol://account/container/blob-name` paths with the container-first
form above. There is no legacy account-prefix detection: the authority is always
a container name. Separate aliases still support separate storage accounts.

Connection strings must identify a public-cloud Azure account and use HTTPS,
with either an account key or SAS. Standard `DefaultEndpointsProtocol`,
`AccountName`, `AccountKey`/`SharedAccessSignature`, `EndpointSuffix` and a matching
public-cloud `BlobEndpoint` are accepted. Standard `QueueEndpoint`, `TableEndpoint`
and `FileEndpoint` fields may also be present when they identify the same account's
public-cloud HTTPS service roots. SAS strings may omit `AccountName` when
`BlobEndpoint` identifies the account. The original string is passed to the SDK.
Custom endpoints and emulator
connection strings are outside this contract. Values stay in the credential
provider; do not put them into SQL.

Format errors identify the rejected rule or numbered entry without printing field
values or unknown field names. These errors happen before client construction;
they do not indicate failed Azure authentication. Check the named rule in the
saved Block. A successful `register_secret` does not establish filesystem format
compatibility: native DuckDB and the filesystem backend use different parsers.

Managed identity uses the configured `account_name` and optional `client_id`.
Omitting the client ID selects the system-assigned identity; supplying it selects
a user-assigned identity. Execute on a host that supports that identity and grant
appropriate storage data permissions. There is no fallback to Azure CLI,
environment credentials, anonymous access or another identity. Workload identity
federation is a separate, unsupported mode. Ambient adlfs storage settings cannot
replace either strategy's selected client.

Registration constructs and publishes a backend; authentication and access checks
may occur on the first discovery/read. Both strategies support file discovery,
CSV/Parquet/blob reads, CSV/Parquet exports and metadata through adlfs. ACL
administration, ADLS Gen1 and Azure Files are outside this feature. Each registration closes its
Azure client and owned identity transport when the session owner finishes.

Local regression tests exercise real DuckDB and adlfs with simulated remote
responses. Live Blob/ADLS Gen2 accounts and managed identities have not yet been
validated; see the [Azure phase](epics/04-filesystems/03-azure-filesystem-strategies.md).

## Enable And Register

Install the optional backend and credential-provider dependencies:

```powershell
poetry install --extras "prefect sftp"
```

A consuming project declares `quackframe[prefect,sftp]` and enables the function:

```toml
[tool.quackframe.functions]
enabled = ["register_filesystem"]
```

Argument order is `provider, reference, filesystem_type, protocol, overrides`.
The last two arguments are optional and default to NULL. Omitted `protocol`
uses the credential reference verbatim. `overrides` is `MAP(VARCHAR, VARCHAR)`.
Registration returns `true` on success and raises on failure. Run registration
as a setup statement before discovery or reads.

Positional, named and mixed arguments are equally supported. These examples are
independent alternatives, each starting in a fresh session. Unless overridden,
the credential references configure `files.example.test` as their endpoint.

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

## Multiple Registrations

Two credential references can connect to the same server with different accounts:

```sql
SELECT quackframe.register_filesystem('prefect', 'supplier-nz-files', 'sftp');
SELECT quackframe.register_filesystem(
    'prefect', 'supplier-au-files', 'sftp', 'supplier-au'
);

SELECT * FROM read_csv('supplier-nz-files://files.example.test/reports/*.csv')
UNION ALL
SELECT * FROM read_csv('supplier-au://files.example.test/reports/*.csv');
```

The protocols select distinct backends. There is no default connection, host-based
credential selection, pooling or global fsspec instance reuse. Additional backend
types must be explicitly implemented and allowlisted; installing a package does
not enable arbitrary filesystem strategies.

## Credentials And Paths

SFTP uses shared `ssh_private_key` credentials. The provider supplies username,
private-key path, port and optional fingerprint. Only `scope` can be overridden
through SQL. Prefect Blocks are one optional provider; the runtime need not be
Prefect. The private-key file must be readable by the executing process.

Scope must be an `sftp://` or `ssh://` URI with a host and no authentication,
query or fragment. Its optional port must agree with the credential port, which
defaults to 22. Scope selects the endpoint; its directory is not prepended to
read paths and is not an access restriction.

Read paths are `protocol://host/absolute/remote/path`. The hostname and effective
port must match the configured endpoint. An omitted read port uses the configured
port. A different hostname is rejected; it never creates or selects another
connection. Embedded authentication, query strings and fragments are rejected.
Server permissions remain the access boundary.

`glob`, file metadata and reader filenames retain the selected protocol and
configured endpoint. Non-default ports appear explicitly in discovered paths.
Discovered filenames are URL-encoded: `report#1.csv` becomes `report%231.csv`.
Reads decode the path once; encoded wildcard characters stay literal, while raw
glob operators such as `*.csv` still select multiple files.

Paths from `glob` can be passed directly to `read_blob` or `read_csv`, including
in later ordered SQL files. No directory-root wrapper is applied.

## Protocol Names And Collisions

Names must match `[a-z][a-z0-9+.-]*`. Hyphens remain intact. If a provider reference
contains underscores or uppercase letters, pass an explicit valid protocol.
There is no automatic name rewriting and no `alias` synonym. `register_secret`
continues using its existing SQL identifier `alias` rules.

Protocols must be unique across all types in the shared DuckDB instance.
Repeated registration fails even with identical configuration. Known fsspec and
DuckDB native schemes are reserved; existing external registrations are checked
before credential loading. DuckDB's Python API does not expose secondary schemes
of arbitrary external wrappers. To prevent ambiguous reads, registration rejects
any pre-existing external Python filesystem not owned by the shared
`SessionResources` context. Register all Python filesystems through that owner;
do not mutate its registrations externally. Native DuckDB readers are unaffected.
Registration
failures leave existing backends intact and close any newly acquired resources.
There is no automatic replacement, unregister SQL function or rollback on SQL
transaction rollback. Protocols and paths must not contain secrets.

## Fingerprint Verification And Concurrent Reads

An optional `host_key_fingerprint` pins the server's OpenSSH SHA256 key
(`SHA256:` plus 43 unpadded base64 characters). Surrounding whitespace is ignored.
Malformed or mismatched fingerprints fail before authentication. Reconnects use
the same policy. Missing, null or blank fingerprints retain automatic acceptance;
this backend does not load `known_hosts`. SQL cannot override the fingerprint.
The separate SSHFS `register_secret` path still warns about nonblank fingerprints
without enforcing them.

Each SFTP client serializes synchronous request/response exchanges with its own
lock. Directory iteration uses synchronous listing through that lock. DuckDB
can still use multiple threads, and independent registrations have independent
locks. The named protocol wrapper delegates to this existing verified adapter.
Asynchronous prefetch, pipelined writes and network deadlines are outside the
verified read contract. Use a bounded worker process to limit stalled-server jobs.

## Registration And Lifetime

Quackframe's runner owns a `SessionResources` context tied to its root DuckDB
connection. Filesystem registration obtains duplicate handles from that root,
so registration performed through a short-lived child does not own the backend's
lifetime. Each registration keeps a handle for eventual unregistration.

After SQL work finishes, cleanup unregisters each filesystem, closes its backend
clients and releases its duplicate handle. The main connection and temporary
storage close afterward. Success, SQL failure and setup failure use the same
cleanup path. Every cleanup is attempted; a cleanup failure raises a safe error,
or adds a safe note to an existing primary exception. No garbage-collection or
process-exit cleanup is required for the owned clients.

For manually installed SQL functions, the caller must provide the owner:

```python
import duckdb
from quackframe import SessionResources
from quackframe.sql_functions.installer import install_functions

with duckdb.connect() as connection, SessionResources(connection) as resources:
    install_functions(connection, ("register_filesystem",), resources)
    connection.execute(
        "SELECT quackframe.register_filesystem('prefect', 'source-files', 'sftp')"
    )
    rows = connection.execute(
        "SELECT * FROM read_csv('source-files://files.example.test/reports/*.csv')"
    ).fetchall()
```

Keep the root connection open until resource cleanup completes. Finish all reads,
including work on duplicate handles, before leaving the resource context. Share
that owner when installing functions on duplicates of the same instance. Do not
use an owner from a different instance. Filesystem protocols do not persist in
a database file and must be registered again for each run.

## Migration And Verification

Before release, named protocols replace standard `sftp://` and `ssh://` reads.
Three-argument calls now register the reference as the protocol. Change read
URLs accordingly. Fourth-position override maps move to fifth position, with a
protocol or NULL in fourth position, or use named `overrides := MAP {...}`.
There is no fallback assigning bare `sftp://` reads to the first registration.

Unit tests exercise SQL forms, isolation, collisions, credential validation and
failure cleanup. Real loopback regressions cover discovery, CSV reads with one
and four threads, fingerprints before authentication, multiple endpoints,
coexisting filesystem types and cleanup while the worker remains alive. External
server and deployed Prefect verification remain environment-specific checks.
Raw-library concurrency diagnostics retain their original upstream failure cases.

## Related Docs

- [Filesystem Write Scope](epics/04-filesystems/04-filesystem-write-support.md): write contract, implementation evidence and remaining live-service validation.
- [Named Protocol Scope](epics/04-filesystems/02-aliased-filesystem-registrations.md): implementation decisions and validation.
- [Previous Filesystem Phase](epics/04-filesystems/01-shared-credential-loading-and-fsspec.md): historical concurrency and lifetime evidence.
- [Credential Providers](credential-providers.md): shared models and provider contracts.
- [SQL Function Extensions](python-extensions.md): explicit enablement and binding.
- [Execution Lifecycle](execution-lifecycle.md): ordered execution and session ownership.
- [Runnable Example](../examples/filesystems/README.md): direct runtime with an optional Prefect credential provider.
