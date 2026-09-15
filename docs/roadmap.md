# Quackframe Roadmap

Status: planning as of 2026-09-15.

This roadmap sequences the smallest implementation that can prove Quackframe's
public contract. Architecture details belong in focused documents; phase status
and validation notes belong in [epic phase files](epics/README.md).

## Phase 0: Repository Foundation

- Add package metadata, `src/quackframe`, tests, linting, formatting, and type
  checking.
- Add public license and contribution guidance.
- Keep Prefect out of required dependencies.

## Phase 1: Configuration And Database Lifecycle

- Implement the typed `QuackframeConfig` model.
- Load `[tool.quackframe]` from `pyproject.toml`.
- Apply environment and direct-value precedence.
- Default the runtime root to the current working directory.
- Decide and implement safe memory, temporary, and persistent database modes.

## Phase 2: Ordered SQL Execution

- Validate a non-empty ordered SQL-file list.
- Open one DuckDB session.
- Use DuckDB to extract and execute statements.
- Stop at the first failure with safe file and statement context.
- Return framework-independent results and exceptions.

## Phase 3: Developer Entry Points

- Expose `quackframe run`.
- Expose a minimal typed Python `run()` API.
- Validate the VS Code F5 launch path against supported configurations.
- Demonstrate scheduled invocation through the same CLI.

## Phase 4: SQL Function Framework

- Define the minimal signature-aware function descriptor.
- Install built-ins through one explicit registry and function-neutral
  registrar.
- Bind the active DuckDB connection for connection-aware functions without
  exposing it to SQL.
- Register private `_quackframe_<name>` Python UDFs.
- Create public `quackframe.<name>` macros.
- Package each function as a self-contained unit of work.

## Phase 5: Runtime Adapter Boundary

- Define the smallest runtime adapter contract.
- Implement first-class direct execution.
- Prove that core tests run without optional runtime packages installed.

## Phase 6: Prefect Runtime

- Add Prefect as an optional dependency.
- Wrap one invocation as a flow and each file as a filename-named task.
- Preserve one shared session, ordering, failure, and no-cache semantics.
- Respect native Prefect profiles and environment settings.

## Phase 7: Credential Function Example

- Implement `quackframe.register_secret` as a self-contained function package.
- Define its private provider contract and registry.
- Implement a Prefect Block provider without coupling it to the Prefect runtime.
- Support `mssql` and `azure_connection_string` secret strategies in the MVP.
- Register temporary DuckDB secrets without returning or logging credentials.

## Early Acceptance Criteria

- A fresh project can install base Quackframe without Prefect.
- CLI, F5, and Python execute the same harmless SQL through one engine.
- Two ordered files share session state and stop on the first failure.
- Configuration resolves predictably from `cwd`, TOML, environment, and direct
  overrides.
- A self-contained Python function is callable as
  `quackframe.<function_name>`.
- The Prefect runtime produces flow and file-level task history without changing
  core execution semantics.
- Prefect credentials can be used with direct or Prefect runtime execution.
- MSSQL and scoped Azure connection-string credentials can be registered as
  temporary DuckDB secrets.
- No standard diagnostic path emits credentials or arbitrary returned data.

## Open Decisions

- Default database mode and derived file location.
- Exact names and fields for Python result and execution-plan types.
- Supported VS Code launch mechanism and fallback.
- Post-MVP external function entry-point discovery and allowlisting contract.
- Whether the first credential function ships in base or as an optional extra.
- Minimum supported Python and DuckDB versions.

## Related Docs

- [Overview](overview.md): product stance and MVP scope.
- [Developer API](developer-api.md): public entry points.
- [Configuration](configuration.md): unresolved database defaults.
- [SQL Function Extensions](python-extensions.md): extension architecture.
- [Epics](epics/README.md): phase-level implementation tracking.
