# Developer Examples

These examples illustrate Quackframe without prescribing repository naming or
layout outside the files needed for the demonstration.

## Run the Active SQL File

Use the launch configuration from the [basic example](../examples/basic/README.md),
open `sql/hello.sql`, and press F5. The launch profile runs:

```powershell
quackframe run "${file}"
```

with the workspace folder as the current working directory.

## Run Ordered Files

```powershell
quackframe run `
    sql/01-prepare.sql `
    sql/02-report.sql
```

The second file can use temporary tables, attachments, macros, and other
session state created by the first. See the [ordered example](../examples/ordered/README.md).

## Embed Quackframe

```python
from quackframe import run

result = run(["sql/hello.sql"])
print(result)
```

The Python API resolves the same `pyproject.toml` and environment inputs as the
CLI.

## Select the Prefect Runtime

```toml
[project]
dependencies = ["quackframe[prefect]"]

[tool.quackframe]
runtime = "prefect"
```

Configure private Prefect connection details through Prefect's native profile
or environment settings. See the [Prefect example](../examples/prefect/README.md).

## Register a Credential Reference

Credential management is an optional SQL-function use case:

```toml
[project]
dependencies = ["quackframe[prefect]"]

[tool.quackframe]
runtime = "direct"

[tool.quackframe.functions]
enabled = ["register_secret"]
```

The function is enabled independently from the selected runtime. Project SQL
can then request an MSSQL secret:

```sql
SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'reporting_reader',
    overrides := MAP {'database': 'Reporting'}
);
```

Azure Storage connection strings use a distinct secret type so later Azure
authentication strategies can coexist:

```sql
SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'analytics-storage',
    secret_type := 'azure_connection_string',
    alias := 'analytics_storage',
    overrides := MAP {'scope': 'az://example-container/reports/'}
);
```

The provider is an operation parameter. Repository-wide provider selection is
not required. The block or an allowed override must supply the database or scope
required by the selected secret type.

See the complete [secret registration example](../examples/secrets/README.md).

## Related Docs

- [Developer API](developer-api.md): the complete entry-point contract.
- [Configuration](configuration.md): checked-in and environment boundaries.
- [Execution Lifecycle](execution-lifecycle.md): shared-session behaviour.
- [Credential Providers](credential-providers.md): the credential example and
  security boundary.
