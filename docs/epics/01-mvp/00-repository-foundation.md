# Repository Foundation

Status: **Planned**
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

## Follow-ups

- Select the supported Python and DuckDB version ranges.
- Select the initial build and dependency-management tooling.
