# Contributing

Quackframe is developed as a SQL-first, framework-independent DuckDB runtime.
Changes should preserve the execution and extension boundaries documented in
[`docs/`](docs/README.md).

## Development

Create the development environment and run the checks:

```powershell
uv sync
uv run pytest
uv run ruff check src tests examples/basic/run.py
uv run ruff format --check src tests examples/basic/run.py
uv run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
```

Install the optional Prefect integration with `uv sync --extra prefect`.

Add focused tests for behaviour changes. Keep project-specific SQL and
credentials out of this repository, and never include secret values in tests,
logs, exceptions, or examples.
