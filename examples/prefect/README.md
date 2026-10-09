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

## Deploy The Quackframe Flow

[deploy.py](deploy.py) imports `quackframe_flow` and calls Prefect's native
`.deploy()` method. No project-owned flow wrapper is needed. Replace the
example image, deployment name, and work pool with your own values, then run
`poetry run python deploy.py`. This registers a deployment; it does not build
or publish the image.

Build and publish your image through your project's normal process, using
Poetry to install a Quackframe version that includes this entry point, with
the `prefect` extra. Include the example's `pyproject.toml` and `sql/` directory
in the image, and configure the **flow execution environment** with:

```text
QUACKFRAME_ROOT=/app
```

The running container must have `/app/pyproject.toml`, `/app/sql/prepare.sql`,
and `/app/sql/report.sql`. Setting the variable on the machine that registers
the deployment does not propagate it to a worker. Use your work pool's native
environment settings or the image's environment. Configure Prefect connection
and authentication through its native settings.

The module entry point imports installed Quackframe in the worker. SQL paths
are not uploads: the project must deliver the files through its image, a
mounted directory, or a checkout prepared before execution. `/app` is only an
example. `QUACKFRAME_ROOT` may differ between environments; when absent,
Quackframe uses the execution process's working directory.

Files are mandatory and run sequentially in the supplied order, sharing one
DuckDB session. `report.sql` uses the temporary table created by `prepare.sql`.
Failure stops later files. Native Prefect schedules and other deployment
options can be passed directly to `.deploy()`.

Optional `config_path` selects an alternate TOML file on the worker;
`config` supplies a complete `QuackframeConfig` instead of loading configuration.
Use one or neither, never both. See the
[flow API](../../docs/developer-api.md#prefect-flow) for precedence and examples.

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
