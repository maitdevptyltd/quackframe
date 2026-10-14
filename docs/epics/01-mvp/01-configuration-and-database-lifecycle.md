# Configuration And Database Lifecycle

Status: **Complete**
Last updated: 2026-10-14
Epic: 01 MVP
Phase: 01
Related docs: [Configuration](../../configuration.md)

## Outcome

Resolve every supported configuration source into one typed,
framework-independent runtime contract.

## Scope

- Implement `QuackframeConfig` and nested database configuration.
- Load `[tool.quackframe]` from `pyproject.toml`.
- Apply environment and direct-value precedence.
- Default runtime root to the current working directory.
- Resolve relative paths from that root.
- Implement the approved memory, temporary, and persistent lifecycle contract.
- Validate writable directories before SQL execution.

## Validation

- Test every precedence layer and invalid combination.
- Test F5-style workspace working-directory resolution.
- Prove persistent paths are never deleted implicitly.
- Prove configuration errors occur before project SQL begins.
- Prove overlapping temporary sessions use distinct generated paths and clean
  up only their own database/WAL files.
- Preserve primary exceptions when database/WAL removal fails; report cleanup-only failures without external error details.

The 2026-10-06 ownership regression failed before the fix. Nine regression cases
now cover competing threads and processes, cleanup ownership, existing files,
connection failure recovery, and SQL failure cleanup. The full suite passed
with 569 tests and four expected upstream SFTP failures. Type checking,
maintained-code lint, formatting, documentation links, and diff checks passed;
repository-wide lint retains 13 existing prototype findings.

The cleanup-error regression also reproduced on 2026-10-06: removal and
reservation-release failures replaced SQL errors, and the CLI returned `2`
instead of `1`. Nine added cases cover successful and failing SQL, individual
cleanup steps, the CLI outcome, and multiple cleanup failures preserving the
original configuration exception or interruption. All 36 focused database and
execution tests pass, as do targeted lint, formatting, type checking,
documentation links, and diff checks. Combined repository validation follows
integration with the other review fixes.

The 2026-10-07 directory-selection regressions reproduced three failures:
explicit temporary paths created the unused default directory, an unavailable
default directory blocked a valid custom path, and default-directory setup
errors escaped the CLI configuration-error handler. Removing eager default
creation leaves preparation to the selected path's existing helper. All 81
focused database, execution, configuration, and CLI tests pass, along with
targeted lint, formatting, type checking, documentation links, and diff checks.

The S03 change on 2026-10-13 supersedes the custom-path reservation behaviour
described in the historical validation above. Generated UUID filenames remove
caller-selected temporary paths and their reservation machinery; persistent
paths and cleanup failure semantics remain unchanged. All 22 targeted database
lifecycle and relevant configuration/CLI cases passed. Ruff on the six changed
Python files and `git diff --check` passed. Sandbox directory permissions
required rerunning the same offline tests outside the sandbox. No broader
validation was run, as requested.

C01 implementation on 2026-10-14 adds Python path-only inference and 13 focused
regression cases. All 26 selected configuration cases passed using a fresh
synthetic temporary directory outside the sandbox after sandbox filesystem
permissions blocked fixture setup. No broader test suite was run.

## Decisions

- Default to an in-memory database.
- Create temporary databases below `<root>/.quackframe/tmp/` and always clean
  them after connection closure.
- Generate every temporary filename under the runtime-root temporary directory,
  reject explicit temporary paths, and report directory setup
  failures as configuration errors.
- Require an explicit path for persistent mode and never delete it implicitly.
- Infer persistent mode from a Python path-only invocation, overriding inherited
  modes while preserving validation of explicitly supplied invocation modes.
- Use exactly `cwd` as the implicit root; do not search parents.
- Keep the original execution, setup, or interruption exception when temporary
  storage cleanup fails. Attach only safe cleanup notes; if cleanup alone fails,
  raise `ConfigurationError`.
