# Developer Entry Points

Status: **In Progress**
Last updated: 2026-09-24
Epic: 01 MVP
Phase: 03
Related docs: [Developer API](../../developer-api.md)

## Outcome

Expose one execution engine through CLI, VS Code F5, and Python entry points.

## Scope

- Add the `quackframe run` command.
- Add the minimal typed Python `run()` API.
- Provide a neutral VS Code launch example over the CLI.
- Keep scheduled execution on the CLI path.
- Add safe exit codes and concise terminal outcomes.

## Validation

- Run equivalent SQL through CLI and Python and compare outcomes.
- Validate F5 on supported VS Code installations.
- Confirm `${workspaceFolder}` supplies the runtime root.
- Test CLI exit codes and help output.

## Open Decisions

- A public `ExecutionPlan` was not needed for the MVP. `run()` accepts the
  ordered paths and a typed configuration directly.
- The basic and Prefect examples use a standard-library Python launcher that
  delegates to Poetry, with output directed to the Debug Console. CLI execution
  and exit-code checks cover the launcher; editor lifecycle validation remains
  necessary before claiming full F5 compatibility across supported installations.
