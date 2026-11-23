# Basic Example

This example runs one harmless SQL file through any supported developer entry
point.

## Command Line

```powershell
quackframe run sql/hello.sql
```

## Visual Studio Code

Open this example directory as the VS Code workspace. Install its dependencies
with `poetry install --no-root` and install the recommended Python extensions.
Poetry must be available on VS Code's PATH, with Python 3.11 or newer available
to start the launcher.

Open `sql/hello.sql` and press F5. The checked-in Python launcher invokes
`poetry run quackframe run` with the workspace folder as the runtime root and
output in the Debug Console. The unannotated query executes and prints the
completion summary; add `-- quackframe: log-result` immediately before a query
to display its result with the default logging setting.

For another downstream repository, copy all three files in `.vscode`:
`launch.json`, `run_quackframe.py`, and `extensions.json`. No particular Poetry
environment location is required. See the
[F5 contract](../../docs/developer-api.md#visual-studio-code-f5) for configuration
overrides and the explicit external-result-logging profile.

## Python

```powershell
python run.py
```

The example configures an explicit persistent path to demonstrate the
caller-owned database lifecycle. Quackframe otherwise defaults to an in-memory
database. Its function allowlist is empty because `hello.sql` uses only native
DuckDB SQL.

For local deployment overrides, add an untracked `.env` beside this README:

```dotenv
QUACKFRAME_DATABASE_PATH=".quackframe/local.duckdb"
```

Quackframe reads this exact runtime-root file without exporting its values to
the process environment. Keep dotenv files out of Git when they contain
secrets or environment-sensitive values.
