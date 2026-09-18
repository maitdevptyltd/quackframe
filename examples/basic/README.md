# Basic Example

This example runs one harmless SQL file through any supported developer entry
point.

## Command Line

```powershell
quackframe run sql/hello.sql
```

## Visual Studio Code

Open `sql/hello.sql` and press F5. The checked-in launch profile invokes the
same command with the workspace folder as the runtime root.

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
