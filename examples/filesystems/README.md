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

## Azure Reads

For the Azure examples, add the `azure` extra to this example's Quackframe
dependency and install it with Poetry. Keep `register_filesystem` enabled.
Create either an `AzureConnectionStringCredentials` Block named
`azure-reports-key`, or an `AzureManagedIdentityCredentials` Block named
`azure-reports-identity`. Configure account `examplestorage` (inside the connection
string for the former) and scope `az://reports/`. Substitute your actual account
in the Block and SQL before running.

```powershell
poetry run quackframe run sql/read-azure-key.sql
poetry run quackframe run sql/read-azure-identity.sql
```

These are independent examples using the direct runtime. Managed-identity reads
require an Azure host with the selected identity and storage data permissions.
The Block's optional `client_id` selects a user-assigned identity; leaving it unset
selects the system-assigned identity. See [Azure filesystems](../../docs/filesystems.md#azure-blob-and-adls-gen2)
for supported connection strings and path semantics.

## Writes

All three strategies support writing with their existing registration. Remote
permissions determine which operations the configured account can perform.
For SFTP, configure an `output-files` Block for a writable destination and run
[write-files.sql](sql/write-files.sql). Its parent `/exports` directory must exist.
For Azure, configure the `azure-reports-key` Block above and run
[write-azure.sql](sql/write-azure.sql); the `reports` container must already exist.
Substitute your own endpoint/account and an intended output path first.

```powershell
poetry run quackframe run sql/write-files.sql
poetry run quackframe run sql/write-azure.sql
```

The examples replace their single output file if it exists. To use managed
identity, change the Azure registration to `azure_managed_identity` and select
its Block reference; the output SQL is otherwise unchanged. See
[write semantics](../../docs/filesystems.md#reads-writes-and-access-control) for
partitioned output, permissions, failure recovery and validation limits.
