# Filesystem Registration

SQL can read wildcard SFTP paths through an optional fsspec filesystem using
credentials already stored in a Quackframe Prefect SSH Block.

## Setup And SQL

Install `quackframe[prefect,sftp]` in the consuming project's Poetry environment.
Enable the function explicitly:

```toml
[tool.quackframe.functions]
enabled = ["register_secret", "register_filesystem"]
```

```sql
SELECT quackframe.register_filesystem('prefect', 'source_files', 'sftp');

SELECT * FROM read_csv('sftp:///exports/*.csv');
SELECT * FROM read_csv('sftp:///exports/**/*.csv');
```

The function returns `true` after successful registration. It uses the shared
credential provider to load `SshPrivateKeyCredentials`, including the existing
underscore-to-dash reference translation. No DuckDB SSH secret is required and
the `sshfs` community extension is not installed by this function.

The Block's `scope` supplies the SSH hostname, and its `port`, `username`, and
`key_path` supply connection settings. The key file must exist in the executing
environment. If scope includes a port it must match the Block's port. The
execution user's SSH `known_hosts` must contain the trusted server key; unknown
hosts are rejected. SSH-agent and automatic key discovery are disabled.

## Boundaries

- SFTP is the only implemented filesystem type. Azure adapters are future work.
- One SFTP endpoint is supported per DuckDB instance. A second registration
  fails before loading credentials or replacing the existing filesystem.
- Use hostless `sftp:///absolute/path` URLs. fsspec binds the filesystem to the
  Block's host; putting another host in a file URL does not select another server.
- Scope's path is not a filesystem root or access restriction. Server-side
  permissions govern accessible files. Reads use absolute remote paths.
- `*` and recursive `**` are supported. SQL files should register the filesystem
  in a separate statement before reading it.
- Registration lasts for the database instance, including duplicate connections,
  and is not persisted across runs. The uncached filesystem releases its SSH
  transport when DuckDB releases it. Failed registration closes it immediately.
- SFTP requests are serialized so concurrent DuckDB readers cannot consume each
  other's responses on the shared channel. Connection and channel waits are
  bounded. This backend prioritizes correctness over parallel SFTP throughput.

`register_secret` retains its existing public signature and behaviour. Both
functions use shared loading code, but each call loads its own credentials.

## Validation

Automated integration tests use an ephemeral loopback SSH server and temporary
private keys to verify direct fsspec globbing, DuckDB wildcard CSV reads, nested
paths, memory and disk databases, duplicate registration, and transport cleanup.
They do not require or read production data.

## Related Docs

- [Credential Providers](credential-providers.md): shared loading and Block compatibility.
- [SQL Function Extensions](python-extensions.md): registration and connection binding.
- [Shared Credentials And SFTP](epics/04-filesystems/01-shared-credentials-and-sftp.md): implementation scope.
