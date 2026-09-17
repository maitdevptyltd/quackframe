# Quackframe Agent Guide

## Project Identity

Quackframe is an orchestrator-agnostic Python runtime for extending and
executing governed, observable DuckDB SQL workflows. SQL is the primary
authoring surface, while Python provides the execution frame and explicit
extension points.

Core execution must work without Prefect or another orchestrator. Prefect is a
first-class optional runtime adapter, and Prefect Blocks are one optional
credential-provider implementation rather than Quackframe's core identity.

README is for humans. This file gives agents the routing, workflow, and
guardrails needed to work in this repository.

## Repository Map

- `src/quackframe/`: package implementation.
- `tests/`: unit and integration tests for core and optional integrations.
- `docs/README.md`: documentation index and knowledge map.
- `docs/*.md`: developer-facing architecture, usage, and examples.
- `docs/epics/[number]-[short-desc]/[phase-no]-[short-desc].md`:
  implementor-facing architecture and phase tracking.
- `examples/`: runnable downstream-project layouts.
- `review-notes/`: temporary accepted review decisions awaiting implementation
  and migration into the documentation that owns the lasting behaviour.
- `.agents/skills/quackframe-documentation/`: documentation workflow skill.
- `.agents/skills/quackframe-coding/`: coding workflow skill.
- `.agents/references/code-style.md`: implementation style and testing
  preferences.
- `.agents/references/preferences.md`: product and workflow preferences.
- `MAD.Utilities.DuckDB/`: prototype evidence only, not an inherited production
  contract.

## Skill Routing

Use focused skills instead of expanding this file with task-specific detail.

- For documentation work, use
  `.agents/skills/quackframe-documentation/SKILL.md`.
- For coding, tests, refactors, runtime adapters, SQL functions, credential
  providers, and implementation work, use
  `.agents/skills/quackframe-coding/SKILL.md`.
- For style and product preferences, read the files in `.agents/references/`.

## Core Guardrails

- Keep core execution independent of Prefect and other orchestrators.
- Keep direct execution first-class. Runtime adapters must preserve ordering,
  shared-session ownership, fail-fast behaviour, cleanup, and result semantics.
- Execute caller-supplied SQL files in explicit order within one shared DuckDB
  session. Do not infer dependencies from folders or filenames.
- Keep SQL as the primary authoring surface and project-specific job behaviour
  outside Quackframe core.
- Keep optional runtime and credential dependencies behind lazy, explicit
  adapters with actionable errors when a selected dependency is unavailable.
- Define credential-provider contracts independently of concrete stores.
  Prefect Blocks must not define the generic credential contract.
- Treat credential resolution as one SQL-extension use case, not the organising
  abstraction of the runner.
- Register built-in SQL functions through an explicit allowlisted registry. Do
  not scan the source tree or expose functions merely because code is installed.
- Keep each non-trivial SQL-callable function self-contained. Prefer limited
  duplication over coupling otherwise independent functions.
- Bind values as parameters in generated SQL. Never place credentials, returned
  query data, or other sensitive values in SQL text, logs, or errors.
- Keep configuration authority in typed models and preserve the boundary
  between checked-in project intent, deployment settings, and invocation
  overrides.
- Keep docs connected through relevant links, like a small knowledge graph.
- Write implementation code like prose: group related ideas with whitespace,
  use clear names, and explain non-obvious intent, ownership, and safety rules.
- Prefer strongly typed public contracts and the smallest clear implementation.
  Add abstractions only when they protect a real extension boundary or reduce
  demonstrated complexity.

## Workflow Expectations

- For non-trivial API, execution, extension, adapter, provider, configuration,
  or architecture changes, establish the developer-facing direction before
  implementation.
- Confirm direction with the user when the public contract or architecture is
  ambiguous or materially changing. Do not block on small fixes or mechanical
  follow-through from an accepted decision.
- Before coding, inspect repository state, nearby tests, relevant docs, and the
  applicable epic phase. Preserve unrelated user changes.
- Add or update tests for behaviour changes.
- Update developer docs and examples when public behaviour changes. Keep epic
  phase docs focused on implementation architecture, sequencing, and status.
- Set a touched phase to `In Progress` when implementation begins and update its
  status before handoff.
- Run relevant tests, lint, type checks, documentation checks, and
  `git diff --check` when available.
- Do not commit unless the user asks. If committing, use a Conventional Commit
  message.

## Validation

Use the checks required by the applicable skill. The standard repository checks
are:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

Run focused tests during development before the full suite. Always report the
checks run and any checks that could not run.
