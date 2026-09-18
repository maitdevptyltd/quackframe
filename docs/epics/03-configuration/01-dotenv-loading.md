# Dotenv Configuration Loading

Status: **Planned**
Last updated: 2026-09-18
Epic: 03 Configuration
Phase: 01
Related docs: [Configuration](../../configuration.md), [Developer API](../../developer-api.md), [Runtime Adapters](../../runtime-adapters.md)

## Outcome

Developers can place Quackframe-owned environment settings in an optional
`.env` file at the runtime root and receive the same validated configuration
as if those values were supplied through the process environment.

This closes the current inconsistency where Prefect can resolve its native
settings from `.env`, while Quackframe settings such as
`QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING` remain unavailable unless another
tool first exports them into the process environment.

## Proposed Scope

- Add `python-dotenv` as a direct core dependency and use its supported parser
  rather than implementing dotenv syntax inside Quackframe.
- Keep Quackframe's existing typed model and explicit source merge. Do not
  migrate configuration to `pydantic-settings` merely to gain dotenv support.
- Read exactly `<runtime-root>/.env` as UTF-8 when `load_config()` resolves
  project configuration. A missing file is a valid no-op.
- Use `dotenv_values()` so configuration loading does not mutate global
  `os.environ` or leak one project's settings into another Python invocation.
- Load dotenv once at the top-level `load_config()` boundary. Nested models,
  runtime adapters, and function providers must not independently reload the
  same file or establish competing precedence rules.
- Pass parsed values through the existing environment-to-model translation and
  Pydantic validation. Dotenv does not become a second configuration model.
- Support the quoting, comments, interpolation, and multiline syntax provided
  by `python-dotenv`, including quoted Boolean values such as `"true"`.
- Apply the following precedence, from highest to lowest:

  1. Explicit CLI or Python arguments.
  2. Existing process environment.
  3. Values from `<runtime-root>/.env`.
  4. Checked-in `[tool.quackframe]` configuration.
  5. Quackframe defaults.

- Keep logging selection and external-result permission out of checked-in
  `pyproject.toml`; `.env` remains an environment-specific input.
- Apply dotenv loading to CLI calls and Python callers that use
  `load_config()`. A caller that supplies an already constructed
  `QuackframeConfig` continues to bypass configuration-source loading.
- Report an unreadable dotenv file as a configuration error before project SQL
  executes. Invalid supported values continue through the existing actionable
  model-validation errors without exposing other dotenv values.

## Ownership Boundaries

- Quackframe consumes only the environment names it explicitly supports. It
  does not copy every dotenv entry into global process state.
- Prefect continues to own `PREFECT_*` parsing, profiles, and precedence.
  Quackframe must not reimplement or override Prefect's native settings model.
- Runtime adapters and SQL-function providers remain responsible for their own
  integration-specific configuration.
- Quackframe never prints dotenv contents or includes secret-bearing values in
  configuration errors.
- Quackframe does not create, edit, commit, or manage `.env` files. Developer
  documentation must recommend excluding secret-bearing dotenv files from Git.
- Dotenv discovery does not search parent directories. Runtime-root ownership
  remains explicit and predictable.

## Implementation Shape

- Add one narrow dotenv-reading helper beside the existing configuration-source
  functions in `src/quackframe/config.py`.
- Merge the parsed dotenv mapping with the supplied or process environment
  before calling the existing `_environment_config()` translator.
- Keep source precedence visible in `load_config()` rather than introducing a
  configuration-provider framework.
- Update the dependency lock, developer configuration documentation, and a
  concise runnable example.

## Assquack Reference

Assquack provides a useful configuration precedent but no dotenv
implementation to reuse. Its Pydantic settings models keep direct values above
process environment values, centralise typed conversion, and explicitly set
`env_file=None` so dotenv behavior cannot arise accidentally.

Quackframe should retain those properties while making the opposite dotenv
decision deliberately: one documented file location, one top-level load, typed
validation through the existing model, and no mutation of global process
state. Assquack's use of `pydantic-settings` does not justify replatforming
Quackframe's established configuration loader.

## Validation

- Prove quoted values in `<runtime-root>/.env` configure runtime selection,
  log selection, external-result permission, database settings, and supported
  DuckDB environment settings.
- Prove dotenv strings receive the same typed conversion and validation as
  process-environment values, including quoted Booleans and path values.
- Prove process environment values override dotenv values.
- Prove explicit CLI and Python values override both process and dotenv values.
- Prove dotenv values override allowed checked-in project settings.
- Prove a missing `.env` preserves current defaults without warning.
- Prove Quackframe does not search a parent directory for `.env`.
- Prove loading one project does not mutate `os.environ` or affect a later
  project loaded in the same Python process.
- Prove nested configuration models and runtime adapters do not reload dotenv
  or change the resolved source precedence.
- Prove unreadable files and invalid supported values fail before SQL execution
  without disclosing unrelated values.
- Prove `QUACKFRAME_ALLOW_EXTERNAL_RESULT_LOGGING="true"` in `.env` permits an
  otherwise valid Prefect result-logging run.
- Prove the direct runtime still works without Prefect installed.

## Non-goals

- Replacing Prefect profiles or Prefect's native dotenv behavior.
- Migrating Quackframe configuration to `pydantic-settings`.
- Supporting multiple dotenv variants such as `.env.local` or
  `.env.production` in the first implementation.
- Searching ancestor directories for dotenv files.
- Expanding environment variables into checked-in TOML values.
- Turning dotenv files into a credential store or logging their contents.

## Open Decision

- Whether `QUACKFRAME_ROOT` may be supplied by the discovered `.env`. The
  recommended first implementation keeps root as a bootstrap input from an
  explicit argument, the process environment, or the current working
  directory; this avoids loading configuration from one root and then silently
  switching to another.
