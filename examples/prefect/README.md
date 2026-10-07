# Prefect Runtime Example

This example selects the optional Prefect runtime adapter while leaving Prefect
connection details outside checked-in configuration.

Configure Prefect through its native profile or environment settings, then run:

```powershell
quackframe run sql/hello.sql
```

The result is one Prefect flow run containing one task named from
`hello.sql`. The SQL and core execution behaviour remain the same as direct
execution.

The function allowlist is deliberately empty. Selecting the Prefect runtime
does not implicitly enable Prefect-backed credentials or another SQL function.

## Visual Studio Code

Open this example directory as the workspace, install dependencies with
`poetry install --no-root`, and install the recommended Python extensions.
Poetry must be on VS Code's PATH and Python 3.11 or newer must be available to
start the launcher. With `sql/hello.sql` active, press F5 to run through Poetry
and show output in the Debug Console.

The `.vscode` folder contains the same portable launcher as the basic example;
copy the entire folder when setting up another downstream repository. The normal
profile does not grant permission to retain query results externally. Use the
explicitly named result-logging profile only when that is intended. For local
direct execution, `.env` may set `QUACKFRAME_RUNTIME=direct`.

See the [F5 contract](../../docs/developer-api.md#visual-studio-code-f5).

Do not add private API URLs, API keys, or other sensitive integration metadata
to this example.
