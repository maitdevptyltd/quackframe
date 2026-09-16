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
