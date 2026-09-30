# Filesystems

SQL workflows can register a standard fsspec filesystem with DuckDB using an
existing credential Block, then read files in the same execution. SFTP is the
first filesystem strategy. It uses the shared SSH credential model and the
ordinary fsspec `SFTPFileSystem`, backed by Paramiko.

## Enable And Register

Install the `sftp` extra for the filesystem and the `prefect` extra when using
Prefect Blocks. From a Quackframe development checkout:

```powershell
poetry install --extras "prefect sftp"
```

A consuming project declares `quackframe[prefect,sftp]` and explicitly enables
the SQL function:

```toml
[tool.quackframe.functions]
enabled = ["register_filesystem"]
```

The provider, reference and filesystem type are required. The optional
`overrides` argument is `MAP(VARCHAR, VARCHAR)`; there is no secret alias.

```sql
SELECT quackframe.register_filesystem('prefect', 'source_files', 'sftp');

SELECT * FROM read_csv('sftp://files.example.test/reports/*.csv');
```

The call returns `true` on success and raises an error on failure. Named
arguments are `provider`, `reference`, `filesystem_type` and `overrides`:

```sql
SELECT quackframe.register_filesystem(
    provider := 'prefect',
    reference := 'source_files',
    filesystem_type := 'sftp',
    overrides := MAP {'scope': 'sftp://files.example.test/reports/'}
);
```

Use one registration per DuckDB instance. These examples show alternative
calls, rather than two registrations to execute together. See the
[runnable example](../examples/filesystems/README.md) for a complete layout.

## Credentials And Paths

`sftp` selects `SftpFilesystem`, whose inherited `credential_type` is
`ssh_private_key`. The Prefect provider loads the existing
`SshPrivateKeyCredentials` Block once and constructs this concrete strategy.
Username, key path and port remain Block-owned; only `scope` may be overridden.
The local private-key file must be readable by the executing process.

After shared override resolution, the SFTP strategy requires an `sftp://` or
`ssh://` URI with a host. Embedded authentication, query strings, fragments and
a URI port conflicting with the Block's port are rejected. An omitted URI port
uses the Block port, which defaults to 22. Both an endpoint-only scope and a
scope containing a directory are accepted.

The scope selects the connection host. Its directory is not prepended to query
paths and is not an access restriction. Full query URLs use the backend's
standard protocol and absolute remote path. fsspec strips the URL authority
when resolving paths on the already-connected backend; a different hostname in
a query does not create or select another SSH connection. Server permissions
remain the access boundary. Quackframe adds no host routing or directory wrapper.

This follows the standard [fsspec SFTP backend](https://filesystem-spec.readthedocs.io/en/latest/_modules/fsspec/implementations/sftp.html)
and [DuckDB filesystem API](https://duckdb.org/docs/stable/guides/python/filesystems).
Backend host-key policy and connection behavior retain their library defaults;
Quackframe adds no SSH trust policy, connection pool or transport serialization.

## Registration And Lifetime

The function registers the filesystem through a short-lived duplicate
connection. DuckDB retains the backend for the shared database instance after
that duplicate closes, so later ordered SQL files can use it. A new database
instance needs a new registration.

DuckDB lists the standard backend as `sftp`; it accepts both `sftp://` and
`ssh://` query URLs. DuckDB 1.5.5
rejects a second registration of an already registered filesystem. Quackframe
does not silently replace the existing backend or maintain an endpoint registry;
the failed new registration closes its newly created SFTP and SSH clients.

Construction uses `skip_instance_cache=True`, avoiding reuse through fsspec's
global instance cache. After successful registration, DuckDB retains the
filesystem object and backend resource cleanup follows DuckDB/fsspec/Paramiko
behavior. Quackframe has no separate session finalizer or transport manager.
Loopback integration tests now establish that closing the DuckDB session can
leave an SSH transport active. Process exit releases that connection, but
persistent-worker cleanup remains unresolved; see the verification boundary below.

Selecting a missing provider or backend gives an actionable installation error.
Core and secret-only execution do not import fsspec or Paramiko. Registration
failures omit backend diagnostics that could include credentials or key paths.

## Verification Boundary

Automated checks cover SQL signatures, NULL and empty override maps, immutable
credential resolution, rejected authentication overrides, one Block load per
call, registration failure cleanup and optional-dependency absence. An
additional test provider and strategy exercise the unchanged loading and SQL
paths, including a DuckDB CSV glob read in a later ordered file.

Real [loopback SFTP tests](../tests/test_sftp_integration.py) reproduce a wildcard
CSV-read hang with four DuckDB threads on DuckDB 1.5.5, fsspec 2026.7.0 and
Paramiko 4.0.0. Extended traces reproduce response mix-ups with concurrent
readers sharing a Paramiko client, including without DuckDB or fsspec.
Independent discovery and one-thread reads return exact results.
For a caller-controlled local mitigation, execute `SET threads = 1` before the
read. This has not yet been verified against the external deployment and does
not resolve the separate connection-cleanup failure after session closure.

The tests use temporary keys, 26 synthetic CSVs, a test credential provider,
and Quackframe's direct runtime without a Prefect server. Children have hard
timeouts and stack capture. Run `poetry run pytest tests/test_sftp_integration.py -v`;
the concurrency and session-cleanup regression assertions currently fail.
The harness itself closes all processes and server resources.

See the [investigation and proposed scope review](epics/04-filesystems/01-shared-credential-loading-and-fsspec.md#loopback-csv-hang-investigation-2026-09-28)
for evidence and remaining deployment checks. There is no automatic fallback:
custom transport or lifecycle changes require a separately accepted scope.

## Related Docs

- [Credential Providers](credential-providers.md): shared models and provider contracts.
- [SQL Function Extensions](python-extensions.md): explicit enablement and installation.
- [Execution Lifecycle](execution-lifecycle.md): ordered execution and session ownership.
- [Filesystem Scope](epics/04-filesystems/01-shared-credential-loading-and-fsspec.md):
  implementation constraints and acceptance evidence.
