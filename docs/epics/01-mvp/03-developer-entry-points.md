# Developer Entry Points

Status: **Planned**
Last updated: 2026-09-15
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

- Whether task-backed VS Code execution is required as a fallback.
- Whether `ExecutionPlan` is necessary in the MVP public API.
