# Secret Registration Example

This example uses the direct runtime while resolving credential references from
Prefect. It demonstrates that runtime selection, provider selection, and SQL
function enablement are independent decisions.

The checked-in `pyproject.toml` enables only `register_secret`. It includes the
Prefect extra because the SQL selects the Prefect credential provider; selecting
the Prefect runtime is not required.

Configure three complete named credentials through Prefect before running the
example:

- `reporting-sql-login`: MSSQL server, database, username, password, and
  optional connection settings;
- `analytics-storage`: an Azure Storage connection string and
  `az://example-container/reports/` scope;
- `source-files`: an SSH username, private-key path, port, and
  `sftp://files.example.test/incoming/` scope.

The names are references only. Do not add credential values, private Prefect
connection details, or environment-specific endpoints to this example.

Run the registrations in one DuckDB session:

```powershell
quackframe run sql/register-secrets.sql
```

Three calls use the preferred three-argument form. Their Prefect documents
contain the complete registration values, and Quackframe derives each DuckDB
alias from its reference. A fourth call demonstrates the optional keyword-style
arguments by repurposing `reporting-sql-login` for the `Warehouse` database and
registering it as `warehouse_reader`.

A real downstream workflow can use those temporary secrets in later ordered
SQL files without exposing credential values.

Per-call overrides remain available for exceptional cases where one stored
authentication credential must deliberately vary by database or scope. They
are not the default configuration path.

The example requires reachable Prefect Block documents and DuckDB extension
installation, so use environment-appropriate test credentials when exercising
it outside this repository.
