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

The example configures an explicit persistent path because Quackframe's default
database lifecycle is still an open design decision.
