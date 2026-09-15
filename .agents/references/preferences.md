# Quackframe Preferences

Use this reference for product and workflow preferences that should survive
across agent sessions.

## Product Direction

- Quackframe is an orchestrator-agnostic runtime for governed, observable
  DuckDB SQL workflows.
- SQL is the primary developer-facing authoring surface. Python provides the
  execution frame and explicit extension points without taking ownership of
  job-specific business logic.
- Core execution must work without Prefect or any other orchestrator.
- Prefect is a first-class optional runtime adapter. Its flow and
  task wrappers may depend on Quackframe; Quackframe core must not depend on
  Prefect.
- Credential resolution is one use case for the Python extension model, not the
  core purpose of the project.
- Credential providers are replaceable adapters. Prefect Blocks are one
  provider implementation and must not define the core credential contract.
- The MVP `quackframe.register_secret` function supports both MSSQL credentials
  and Azure connection-string credentials. Use the public secret-type names
  `mssql` and `azure_connection_string`.
- Execute caller-supplied SQL files in explicit order within one shared DuckDB
  session. Do not infer dependencies or ordering from folders or filenames.
- Keep direct execution first-class. Selecting a runtime adapter should
  not silently change ordering, caching, retry, concurrency, or failure
  semantics.
- Keep project-specific SQL, database names, organizational conventions, and
  job behaviour in consuming repositories.
- Do not turn Quackframe into a general workflow engine, DAG scheduler,
  credential store, or copy-specific framework.
- Treat each SQL-callable function as a self-contained unit of work. Prefer
  limited duplication over shared abstractions that restrict independent
  functions. Require only the minimal contract needed for naming,
  registration, safety, and coexistence.
- Register MVP built-in SQL functions through one explicit, reviewable registry.
  Do not scan the source tree or expose functions merely because a module is
  installed. Third-party discovery is post-MVP and must remain allowlisted.
- Keep SQL-function installation neutral: the registrar and execution runner
  must not branch on concrete function names, providers, or function-specific
  request types.
- Support connection-aware functions by binding the active DuckDB connection
  outside the SQL-visible signature. Inspect and validate callable signatures
  so optional SQL arguments can be represented by generated macros.
- Use a typed `QuackframeConfig` model as configuration authority. Load stable,
  shareable project intent from `[tool.quackframe]`, use environment or native
  integration settings for deployment-specific and sensitive values, and use
  CLI or direct Python values for one-run overrides.
- Default the runtime root to the current working directory when no explicit
  root is supplied.

## Documentation Direction

- Keep `docs/README.md` as the documentation index.
- Treat docs like a knowledge graph: each active architecture page should link
  to adjacent pages through `## Related Docs`.
- Keep developer-facing concepts separate from implementor-facing epic phase
  tracking.
- Use Mermaid diagrams when they clarify architecture, execution flow,
  extension boundaries, state transitions, or adapter ownership.
- Treat `MAD.Utilities.DuckDB` as prototype evidence, not as Quackframe's
  documentation structure or an automatically accepted production contract.
- Treat `assquack` as documentation-structure reference only. Its product goals
  and functionality do not constrain Quackframe.

## Public Documentation Language

- Write public documentation for the general open-source community, not around
  MAIT DEV's internal customers, infrastructure, tenancy model, or repository
  naming conventions.
- Use neutral example names such as `analytics-workflows/`, `example.sql`, and
  `your-project`. Examples must illustrate Quackframe without prescribing how
  consumers name or organize unrelated repositories.
- Mention MAIT DEV systems or repository names only when identifying explicit
  prototype provenance or another source that materially informs Quackframe.
- Translate useful prototype behaviour into general product language rather
  than carrying internal terminology into the public contract.

## Agent Workflow Preferences

- For non-trivial feature, API, execution, extension, adapter, or architecture
  changes, establish the developer-facing direction before implementation.
- Confirm direction with the user when a change affects the public API,
  architecture, execution semantics, or integration boundaries and the desired
  direction is not already explicit.
- Do not block for confirmation on small, obvious bug fixes or mechanical
  follow-through from an approved direction.
- Add or update tests with behaviour changes. If tooling does not exist yet,
  report the gap and add tests once the package scaffold exists.
- Run relevant tests, lint, type checks, documentation checks, and
  `git diff --check` before final handoff when available.
- Prepare Conventional Commit wording when useful, but commit only when the
  user asks.
- Treat the working tree and staging area as user-controlled. Preserve existing
  hunks, do not unstage or revert unrelated changes, and ask before touching a
  file when preserving another author's edits is not feasible.
- Keep handoffs reviewable: describe what changed, why it changed, checks run,
  blockers, and remaining decisions.
