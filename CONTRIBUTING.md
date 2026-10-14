# Contributing

Quackframe is developed as a SQL-first, framework-independent DuckDB runtime.
Changes should preserve the execution and extension boundaries documented in
[`docs/`](docs/README.md).

## Development

Create the development environment and run the checks:

```powershell
poetry install
poetry run pytest
poetry run ruff check src tests scripts examples/basic/run.py
poetry run ruff format --check src tests scripts examples/basic/run.py
poetry run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
```

Install the optional Prefect integration with
`poetry install --extras prefect`.

Install local SFTP test dependencies with `poetry install --extras sftp`.
The default pytest run excludes only four unprotected upstream SFTP concurrency
controls (Paramiko/fsspec, four threads, traced/untraced). These reproduce known
upstream deadlocks or packet races and can each wait 60 seconds. Single-thread
library cases and Quackframe's protected SFTP regressions remain enabled.
To deliberately run the four controls, overriding the default marker filter:

```powershell
poetry run pytest tests/test_sftp_integration.py -m upstream_sftp_control -v
```

Append `--collect-only` to inspect their selection without executing them.

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
