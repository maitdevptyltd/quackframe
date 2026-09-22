# Secret Registration Example

This example uses the direct runtime while resolving credential references from
Prefect. It demonstrates that runtime selection, provider selection, and SQL
function enablement are independent decisions.

The checked-in `pyproject.toml` enables only `register_secret`. It includes the
Prefect extra because the SQL selects the Prefect credential provider; selecting
the Prefect runtime is not required.

Configure three named credentials through Prefect before running the example:

- `shared-sql-login`: MSSQL server, username, password, and optional connection
  settings, with no database required;
- `analytics-storage`: an Azure Storage connection string, with no scope
  required.
- `source-files`: an SSH username, private-key path, port, and
  `sftp://files.example.test` scope.

The names are references only. Do not add credential values, private Prefect
connection details, or environment-specific endpoints to this example.

Run both registrations in one DuckDB session:

```powershell
quackframe run sql/register-secrets.sql
```

The SQL reuses `shared-sql-login` to create `reporting_reader` and
`warehouse_reader` for two databases. It also supplies the Azure scope while
creating `analytics_storage`. A real downstream workflow can use those
temporary secrets in later ordered SQL files without exposing credential
values.

The private-key SSH registration narrows `source-files` to an example incoming directory.
The username, key path, and port remain protected in Prefect while reviewed SQL
may replace only the non-sensitive scope.

The example requires reachable Prefect Block documents and DuckDB extension
installation, so use environment-appropriate test credentials when exercising
it outside this repository.
