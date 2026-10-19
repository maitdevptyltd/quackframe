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

[CI](.github/workflows/ci.yml) preserves Windows core-only Python 3.11/3.13
coverage and tests both optional extras on Windows 3.11/3.13/3.14 and Linux
3.11/3.14. The Windows 3.11 extras case checks the minimum supported Prefect.
On every PR, a separate Linux Python 3.14 job builds the source distribution and
wheel, checks both with Twine, and runs the existing clean-wheel Python/CLI smoke
test in a separate Poetry project without extras. This checks the source metadata
version; release version stamping and publication remain in the Release workflow.

Feature and candidate-fix PRs target `release/next`; compatible fixes to an
existing stable release may target `main`. Use Conventional Commit messages and
preserve breaking-change footers in the final merged history. Promotion from
`release/next` to `main` uses an ancestry-preserving merge, not squash.

The [release guide](docs/releases.md) defines automatic candidates, stable
promotion, patch releases, package validation, owner setup and recovery.
