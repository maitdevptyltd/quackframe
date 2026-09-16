# Repository Foundation

Status: **Complete**
Last updated: 2026-09-15
Epic: 01 MVP
Phase: 00
Related docs: [Roadmap](../../roadmap.md)

## Outcome

Create a public Python library repository that can support independently tested
core and optional integrations.

## Scope

- Add `pyproject.toml`, lock file, `src/quackframe`, and `py.typed`.
- Add pytest, Ruff, formatting, and type-checking configuration.
- Add public CI, license, and contribution guidance.
- Define base and optional Prefect dependency groups.
- Add import tests proving base Quackframe does not require Prefect.

## Validation

- Clean base installation succeeds without optional integrations.
- Package imports and CLI help succeed.
- Lint, format, type, test, and documentation checks run in CI.

Implemented with a `src`-layout Hatchling package, uv lock file, Ruff, Pyright,
pytest, Windows CI, an MIT license, and an optional `prefect` extra. The base
package imports without loading Prefect.

## Follow-ups

- Add further operating-system jobs when supported environments require them.
