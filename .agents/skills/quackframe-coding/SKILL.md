---
name: quackframe-coding
description: Implement Quackframe code changes. Use when Codex is asked to scaffold package code, add or change Python behaviour, implement DuckDB SQL execution, runtime adapters, observability, SQL-callable Python extensions, credential providers, configuration, tests, bug fixes, refactors, release-quality implementation work, or developer-facing docs and epic phase status as part of a code change.
---

# Quackframe Coding

## Overview

Use this skill for implementation work in Quackframe. Keep core execution
orchestrator-agnostic, keep SQL as the primary authoring surface, and place
external runtime and credential systems behind explicit adapters.

Before coding, read:

- `.agents/references/preferences.md`
- `.agents/references/code-style.md`
- relevant docs in `docs/`, especially `overview.md`, `developer-api.md`,
  `execution-lifecycle.md`, `runtime-adapters.md`, `python-extensions.md`,
  `credential-providers.md`, and `configuration.md` when they exist

## Workflow

1. Inspect repository state, instructions, relevant docs, nearby code, tests,
   project metadata, and the explicitly identified prototype seams.
2. Identify whether the request changes public API, execution semantics,
   session ownership, observation, extensions, adapters, credential providers,
   configuration, or migration posture.
3. For non-trivial changes, check for a relevant epic phase under
   `docs/epics/**`. Create or update it with implementor-facing direction,
   scope, boundaries, and validation. Update regular developer-facing docs when
   public behaviour or usage changes. Confirm with the user when direction is
   ambiguous or materially changes an approved contract.
4. Implement the narrowest coherent change that satisfies the request.
5. Add or update tests for behaviour changes.
6. Keep docs in their lanes: regular docs help developers use Quackframe; epic
   phase docs help implementors understand architecture, sequencing, and
   status. Use the `quackframe-documentation` skill for substantial docs work.
7. Update the status header for relevant epic phases before handing work back.
8. Run relevant tests, lint, type checks, docs checks, and `git diff --check`.
9. Review the diff for unrelated edits, regressions, unsafe data exposure, and
   terminology or dependency-boundary drift.
10. If the user asks for a commit, use a Conventional Commit message.

Do not pause for confirmation on small, obvious fixes or mechanical
follow-through from an approved direction.

## Implementation Rules

- Core Quackframe code must not import Prefect or another orchestrator.
- Optional runtime adapters own framework decorators and translate external
  lifecycle concepts to Quackframe core calls.
- Core execution must remain usable without optional integrations installed.
- Keep ordered execution, shared-session ownership, fail-fast behaviour,
  cleanup, and core result semantics independent of the selected adapter.
- Do not silently enable retries, caching, concurrency, or reordered execution
  in a runtime adapter.
- Define credential-provider contracts independently of Prefect. Prefect Blocks
  are one optional provider implementation.
- Treat credential management as an extension use case, not the organising
  abstraction of the runner.
- Keep project-specific SQL and job behaviour outside Quackframe core.
- Keep each non-trivial SQL function in its own self-contained package. Prefer
  local duplication over coupling independent functions through shared
  theme-level implementation.
- Prefer explicit, strongly typed contracts for execution plans, sessions,
  results, observers, registries, runtime adapters, and providers.
- Treat code as liability. Prefer the smallest clear implementation and add
  patterns only where they clarify a real extension boundary.
- Shape code into readable paragraphs and use narrative comments or docstrings
  only when names do not make the intent or invariant clear.
- Use parameter binding for values in SQL.
- Centralise and test generated identifiers, SQL quoting, redaction, and
  exception conversion.

## Testing Expectations

- Test the core package with optional orchestrator and provider dependencies
  absent.
- Test ordered single-file and multi-file execution in one DuckDB session.
- Test failure attribution, fail-fast behaviour, cleanup policies, and safe
  output that excludes credentials and returned query data.
- Test runtime adapters preserve core execution semantics while producing the
  intended external runtime records.
- Test SQL-callable extension registration, optional arguments, validation,
  and connection ownership.
- Test credential-provider contracts separately from concrete provider
  implementations.
- Use temporary `.duckdb` files for disk-backed behaviour.
- If tooling is not scaffolded, state exactly which checks could not run.

## Done Criteria

A coding task is done when:

- code implements the requested behaviour;
- relevant tests are added or updated;
- relevant developer-facing docs and examples are updated;
- relevant implementor-facing epic phase docs are current;
- core remains independent of optional frameworks and providers;
- available checks pass, or unavoidable gaps are reported;
- the final response lists changed areas and verification;
- no unrelated user changes are reverted.
