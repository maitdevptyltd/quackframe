# Filesystem Examples

Read remote CSV files through DuckDB's standard fsspec integration while using
the direct runtime and an existing Prefect SSH credential Block.

Install this example's `quackframe[prefect,sftp]` dependency with Poetry. Configure
Prefect through its native settings, and save a Quackframe
`SshPrivateKeyCredentials` Block named `source-files` containing the username,
local private-key path, port and `sftp://files.example.test/` scope. Substitute
your test server in the Block and the SQL query path before running.

Optionally set `host_key_fingerprint` to the server administrator's verified
OpenSSH `SHA256:...` fingerprint. Registration refuses a mismatched key. Leave
the field unset or blank to preserve connections without host-key verification.
The SQL example requires no changes.

From this directory:

```powershell
poetry run quackframe run sql/read-files.sql
```

The first statement registers protocol `source-files`; the second reads remote
CSVs through `source-files://files.example.test/reports/*.csv`. The protocol
defaults to the credential reference. An explicit fourth positional argument or
`protocol := 'another-source'` selects a different protocol.
The function is explicitly enabled in [pyproject.toml](pyproject.toml), and no
Prefect runtime or DuckDB SSH extension is required. Credential values belong
in the Block, and the private-key file remains on the executing machine.

The scope's directory does not restrict access or rewrite query paths. Use
absolute remote paths and test the standard backend's globbing, concurrent
reads against your server. Quackframe explicitly closes registered clients at
the end of the run. See [Filesystems](../../docs/filesystems.md)
for protocol collision and lifetime behavior.

## Writes

SFTP supports writing with its existing registration. Remote permissions determine
which operations the configured account can perform. Configure an `output-files`
Block for a writable destination and run [write-files.sql](sql/write-files.sql).
Its parent `/exports` directory must exist. Substitute your SFTP endpoint and
intended output paths first.

```powershell
poetry run quackframe run sql/write-files.sql
```

The example replaces its single output file if it exists. See
[write semantics](../../docs/filesystems.md#reads-writes-and-access-control) for
partitioned output, permissions, failure recovery and validation limits.

For Azure reads and writes, use native DuckDB Azure secrets through
`register_secret`; see the [secret examples](../secrets/README.md) and
[Azure access](../../docs/filesystems.md#azure-blob-and-adls-gen2). The Python
Azure fsspec strategies and `azure` extra have been removed.
