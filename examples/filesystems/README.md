# SFTP Filesystem Example

Read remote CSV files through DuckDB's standard fsspec integration while using
the direct runtime and an existing Prefect SSH credential Block.

Install this example's `quackframe[prefect,sftp]` dependency with Poetry. Configure
Prefect through its native settings, and save a Quackframe
`SshPrivateKeyCredentials` Block named `source-files` containing the username,
local private-key path, port and `sftp://files.example.test/` scope. Substitute
your test server in the Block and the SQL query path before running.

From this directory:

```powershell
poetry run quackframe run sql/read-files.sql
```

The first statement registers the backend; the second reads remote CSV files.
The function is explicitly enabled in [pyproject.toml](pyproject.toml), and no
Prefect runtime or DuckDB SSH extension is required. Credential values belong
in the Block, and the private-key file remains on the executing machine.

The scope's directory does not restrict access or rewrite query paths. Use
absolute remote paths and test the standard backend's globbing, concurrent
reads and cleanup against your server. See [Filesystems](../../docs/filesystems.md)
for protocol collision and lifetime behavior.
