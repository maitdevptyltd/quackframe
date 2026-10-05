# Contributing

Quackframe is developed as a SQL-first, framework-independent DuckDB runtime.
Changes should preserve the execution and extension boundaries documented in
[`docs/`](docs/README.md).

## Development

Create the development environment and run the checks:

```powershell
poetry install
poetry run pytest
poetry run ruff check src tests examples/basic/run.py
poetry run ruff format --check src tests examples/basic/run.py
poetry run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
```

Install the optional Prefect integration with
`poetry install --extras prefect`.

Add focused tests for behaviour changes. Keep project-specific SQL and
credentials out of this repository, and never include secret values in tests,
logs, exceptions, or examples.

## Releases

Feature and candidate-fix PRs target `release/next`; compatible fixes to an
existing stable release may target `main`. Use Conventional Commit messages and
preserve breaking-change footers in the final merged history. Promotion from
`release/next` to `main` uses an ancestry-preserving merge, not squash.

The [release guide](docs/releases.md) defines automatic candidates, stable
promotion, patch releases, package validation, owner setup and recovery.
