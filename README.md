# Quackframe

Extend and execute DuckDB SQL workflows through a small Python runtime.

Quackframe executes explicitly ordered SQL files in one shared DuckDB session.
Use it directly from the command line or Python, or install the optional Prefect
adapter to represent the same execution as a flow with filename-named tasks.

```powershell
pip install quackframe
quackframe run sql/example.sql
```

```python
from quackframe import run

result = run(["sql/01-prepare.sql", "sql/02-report.sql"])
```

The base package does not depend on Prefect. Install `quackframe[prefect]` only
when using the Prefect runtime or Prefect-backed credential Blocks.

Start with the [documentation index](docs/README.md), the
[developer API](docs/developer-api.md), or the
[runnable examples](examples/README.md).
