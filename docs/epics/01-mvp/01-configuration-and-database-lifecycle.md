# Configuration And Database Lifecycle

Status: **Complete**
Last updated: 2026-10-06
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
- Reproduce overlapping temporary-path acquisition and prove that reservation
  covers connection setup, SQL execution, and database/WAL cleanup.
- Preserve primary exceptions when database/WAL removal or reservation release
  fails; report cleanup-only failures without external error details.

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

## Decisions

- Default to an in-memory database.
- Create temporary databases below `<root>/.quackframe/tmp/` and always clean
  them after connection closure.
- Require an explicit path for persistent mode and never delete it implicitly.
- Use exactly `cwd` as the implicit root; do not search parents.
- Atomically create a sibling reservation directory before checking a temporary
  database and its WAL. Hold it until cleanup finishes; contenders never acquire
  file ownership. Existing database or WAL files are never adopted.
- Keep the original execution, setup, or interruption exception when temporary
  storage cleanup fails. Attach only safe cleanup notes; if cleanup alone fails,
  raise `ConfigurationError`.
