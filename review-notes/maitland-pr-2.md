# PR 2 — Maitland review checklist

Status: **Open**
Last updated: 2026-10-16
Review: 2026-10-08, commit `a7ab17974d25a5c9289fbacef22db4a9144e9324`

[Pull request](https://github.com/maitdevptyltd/quackframe/pull/2) · [Maitland's overview](https://github.com/maitdevptyltd/quackframe/pull/2#pullrequestreview-5449915627) · [Documentation index](../docs/README.md)

This is a temporary working checklist of Maitland's feedback, not a new public
contract. Summaries below are paraphrases; linked GitHub comments are authoritative.
All 28 inline comments are represented once. Overview-only actions are separate.

A checked box means implemented, clarification requested, deliberately declined,
or assigned an agreed follow-up; it does not mean every item has shipped. Record the decision, implementation/commit, and verification in its
resolution field. Local completion does not resolve a GitHub review thread.
Move lasting decisions into their owning docs before retiring this checklist.

## Overview

Maitland supports the core architecture. He asks for targeted fixes, a smaller
0.1.0 scope and smaller future PRs. Release tooling may merge while publication
remains disabled; activation needs the release findings addressed. His reported
validation was 628 passed and 4 xfailed on Windows/Python 3.11 with all extras,
with lint, type and documentation checks clean. This checklist does not independently
rerun those results. The reconciliation below records current local implementation
status and previously completed verification.

## Reconciled status — 2026-10-16

This table covers **32 tracking entries: 28 inline comments and four overview
items**, not 32 separate comments. Detailed decisions and verification evidence
follow below. Verification results are recorded evidence, not tests rerun during
this documentation reconciliation.

| ID | Item | Current status | Commit / reference |
| --- | --- | --- | --- |
| S01 | Azure fsspec removal | Complete; re-review clear | 68cf333, 16a4468 |
| S02 | DuckDB SSHFS route | Addressed: awaiting clarification | Comment 4255240046; no removal |
| S03 | Temporary database paths | Complete | 841323d |
| S04 | Release recovery machinery | Not started; decision needed | — |
| S05 | Separate flow work | Agreed separate PR; outside this checklist’s remaining work | — |
| R01 | Useful errors and output routing | Complete and reviewed on logging branch; integration pending | fbbcb71, e7652a9, f8259ed |
| R02 | Complete result execution | Complete | 476aff5 |
| R03 | Base NumPy dependency | Complete; clean wheel verified | af93d25, 9b19e0d |
| R04 | TOML extension loading | Addressed: awaiting clarification | db03680; comment 4267371558 |
| R05 | Empty function installation | Complete; five targeted checks passed | be1ab72, 9b19e0d |
| R06 | Progress logging | Not started; separate logging work | — |
| R07 | Result selection and annotations | Not started; separate logging work | — |
| C01 | Python database-path mode | Complete; example updated | d88cd5f, 09d697d |
| C02 | Configuration runtime root | Complete | 6e2be2f |
| C03 | Typed DuckDB settings | Complete | 22c1491 |
| C04 | Home-directory expansion | Complete | ae0bd71 |
| C05 | TOML authority | Complete | 439302c |
| C06 | DuckDB compatible range | Complete | 7fe2f92 |
| C07 | fsspec upper bound | Addressed: awaiting clarification | 3deccbc; comment 4266977546 |
| V01 | Linux and package CI | Committed; local smoke passed; hosted matrix pending | 642a090 |
| V02 | Opt-in upstream controls | Complete; collection verified | c537209 |
| V03 | Repository cleanup | Complete; package inventories and targeted checks passed | 67d279b, 2aa2c02, a42732d |
| V04 | Credential table | Complete | d387309 |
| P01 | PyPI verification polling | Complete | c3b2928 |
| P02 | Trusted release execution | Code complete; external environment setup outstanding | b670ec5 |
| P03 | Workflow hardening | Complete | efaf00f |
| P04 | RC ancestry | Complete | 466029f |
| P05 | Before first stable | Complete | 6772e06 |
| O01 | Contributor lint commands | Complete | d387309 |
| O02 | Python 3.14 coverage | Committed; shares V01 hosted verification | 642a090 |
| O03 | Monotonic timing | Complete | ee28c83 |
| O04 | Smaller future PRs | Accepted future guidance; no current implementation task | — |

### Branch and verification handover

- `fix/pr-2-feedback` was clean at `642a090` before this tracker update and
  27 commits ahead of the locally recorded `origin/fix/pr-2-feedback`.
  This reconciliation does not push changes or refresh remote refs.
- `refactor/error-logging` is clean at `f8259ed`, in worktree
  `C:/Users/RowanFarquharson/.codex/worktrees/6e53/quackframe`.
  Its three exclusive commits are `fbbcb71`, `e7652a9` and `f8259ed`.
  They are not integrated into `fix/pr-2-feedback`; the logging branch has no
  configured remote tracking branch. The recorded work was not pushed.
- The last verified PR head was `feat/setup` at `a7ab179`; do not describe local
  feedback fixes as already present in the PR. Live PR state was not rechecked
  during this local reconciliation.
- Remaining implementation decisions/work: **S04, R06 and R07**. Remaining
  delivery/setup: integrate R01, run hosted V01/O02 verification, and finish
  P02 environment configuration before enabling publication.
- **S02, R04 and C07 are addressed pending reviewer clarification**, not active
  implementation tasks. Reply state is from the last recorded PR check; check
  for a response before reopening them. S05 is agreed separate work; O04 is
  future guidance. Neither belongs on the current implementation to-do list.
- Keep validation targeted. No full suite, broad formatting or new review loop
  is implied by this handover. Local Windows/Python 3.14 and Linux/Python 3.11
  clean-wheel checks passed; this does not establish hosted Linux/Python 3.14
  or optional-extras matrix success.

## Navigation

- [Scope decisions](#scope-decisions)
  - [S01: Azure fsspec](#s01-azure-fsspec)
  - [S02: DuckDB SSHFS](#s02-duckdb-sshfs)
  - [S03: Custom temporary database paths](#s03-custom-temporary-database-paths)
  - [S04: Release recovery machinery](#s04-release-recovery-machinery)
  - [S05: Separate flow work](#s05-separate-flow-work)
- [Runtime and diagnostics](#runtime-and-diagnostics)
  - [R01: Useful SQL errors](#r01-useful-sql-errors)
  - [R02: Result logging executes the complete query](#r02-result-logging-executes-the-complete-query)
  - [R03: NumPy dependency](#r03-numpy-dependency)
  - [R04: Community extensions](#r04-community-extensions)
  - [R05: Read-only databases](#r05-read-only-databases)
  - [R06: Progress logging](#r06-progress-logging)
  - [R07: Result statement selection and annotations](#r07-result-statement-selection-and-annotations)
- [Configuration and dependencies](#configuration-and-dependencies)
  - [C01: Python database-path consistency](#c01-python-database-path-consistency)
  - [C02: Relative configuration paths](#c02-relative-configuration-paths)
  - [C03: Typed DuckDB settings](#c03-typed-duckdb-settings)
  - [C04: Home-directory expansion](#c04-home-directory-expansion)
  - [C05: TOML configuration authority](#c05-toml-configuration-authority)
  - [C06: DuckDB version constraint](#c06-duckdb-version-constraint)
  - [C07: Calendar-version dependency caps](#c07-calendar-version-dependency-caps)
- [Validation and repository cleanup](#validation-and-repository-cleanup)
  - [V01: Linux and package CI](#v01-linux-and-package-ci)
  - [V02: Opt-in upstream deadlock controls](#v02-opt-in-upstream-deadlock-controls)
  - [V03: Public repository cleanup](#v03-public-repository-cleanup)
  - [V04: Credential documentation table](#v04-credential-documentation-table)
- [Before enabling releases](#before-enabling-releases)
  - [P01: PyPI verification delay](#p01-pypi-verification-delay)
  - [P02: Trusted release execution](#p02-trusted-release-execution)
  - [P03: Workflow hardening](#p03-workflow-hardening)
  - [P04: RC and patch ancestry](#p04-rc-and-patch-ancestry)
  - [P05: Before the first stable release](#p05-before-the-first-stable-release)

## Scope decisions

### S01 Azure fsspec

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323284) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/sql_functions/register_filesystem/azure.py#L153)
- Feedback: Consider removing Azure fsspec strategies in favour of native DuckDB Azure reads/writes. Identify any unmet requirement before removal.
- Decision: Approved: remove Azure fsspec strategies and their unused extra/dependencies. Retain shared credential loading, Azure models and Prefect support, native DuckDB Azure secrets, SFTP and shared filesystem ownership. No downstream migration or SSHFS removal in S01.
- Resolution / verification: Implemented in the commit containing this entry (`refactor: remove Azure fsspec strategies`). Removed the two filesystem strategies, Azure backend, Azure-only tests/examples and unused dependencies; retained shared credential/provider architecture, native Azure secrets and SFTP. Poetry preserved every surviving locked version and added no packages. The selected unit cases passed (51 passed, 25 deselected); two synthetic localhost SFTP export cases passed. The first export-test attempt failed on sandbox temporary-directory permissions before execution; the same two cases passed with normal escalation and a fresh ignored directory. No live customer services, customer data, credentials or `.env` reads; no full suite, broad checks/builds, downstream changes, push or GitHub thread changes. Changed-file Ruff and Pyright passed; Pyright required normal escalation to resolve installed Poetry dependencies after two sandboxed attempts reported missing imports. Separate review identified stale filesystem write documentation, corrected in `16a4468`; the follow-up review found no remaining scoped issues. Implementation commit: `68cf333`.

Exact successful checks:

```powershell
poetry lock
poetry run pytest tests/test_credential_loading.py::test_loading_preserves_strategy_and_saved_values tests/test_register_secret.py tests/test_prefect_integration.py::test_prefect_provider_translates_azure_block tests/test_prefect_integration.py::test_prefect_provider_translates_azure_managed_identity_block tests/test_prefect_integration.py::test_both_sql_functions_load_one_block_each_and_construct_the_requested_strategy tests/test_register_filesystem.py::test_unknown_type_fails_before_loading tests/test_register_filesystem.py::test_sftp_constructor_and_endpoint_mapping tests/test_register_filesystem.py::test_sql_forms_read_and_discover_the_selected_protocol tests/test_register_filesystem.py::test_failed_duckdb_registration_closes_new_backend tests/test_resources.py::test_resource_cleanup_attempts_all_and_preserves_primary_error tests/test_filesystem_writes.py::test_deferred_errors_never_expose_backend_payloads tests/test_filesystem_writes.py::test_sftp_close_acknowledgement_failure_is_not_suppressed tests/test_filesystem_writes.py::test_file_cleanup_preserves_primary_failure -k 'not test_register_secret or azure' -q -p no:cacheprovider --basetemp=.test-tmp-s01-unit-01 --tb=short
poetry run pytest 'tests/test_filesystem_writes.py::test_sftp_exports_and_reads_back[0-False-CSV]' 'tests/test_filesystem_writes.py::test_sftp_exports_and_reads_back[10000-True-PARQUET]' -q -p no:cacheprovider --basetemp=.test-tmp-s01-exports-02 --tb=short
poetry run ruff check --no-cache src/quackframe/sql_functions/register_filesystem/models.py tests/test_credential_loading.py tests/test_filesystem_writes.py tests/test_register_filesystem.py
poetry run pyright --pythonpath E:/projects/quackframe/.venv/Scripts/python.exe src/quackframe/sql_functions/register_filesystem/models.py tests/test_credential_loading.py tests/test_filesystem_writes.py tests/test_register_filesystem.py
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

The `-k` selection includes only Azure cases from `test_register_secret.py`;
other explicitly selected nodes cover retained credential and filesystem contracts.

### S02 DuckDB SSHFS

- [x] Addressed — awaiting clarification
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323290) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/sql_functions/register_secret/models.py#L145) · [Local file](../src/quackframe/sql_functions/register_secret/models.py)
- Feedback: Consider removing register_secret(..., 'ssh_private_key'), retaining fsspec SFTP. Review existing callers before removal.
- Decision: Discussed: keep shared SSH credential models, credential providers and Prefect Blocks. Only the DuckDB SSHFS registration route is proposed for removal. Older downstream code has callers; migration remains unverified.
- Resolution / verification: [Clarifying comment posted](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4255240046). Retain the credential/block structure for the current fsspec route and possible future SSHFS support once extension gaps are fixed. No removal implemented; await the reviewer response before further action.

### S03 Custom temporary database paths

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323295) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/database.py#L87) · [Local file](../src/quackframe/database.py)
- Feedback: Consider generating every temporary database filename automatically, removing custom temporary paths and associated reservation machinery. Reviewer explicitly says this is not a blocker.
- Decision: Approved: generate every temporary filename below `<root>/.quackframe/tmp/`; reject explicit temporary paths. Persistent paths and retention remain unchanged.
- Resolution / verification: Implemented in the commit containing this entry (`fix: generate all temporary database paths`). Removed custom-path reservation/locking, retained owned database/WAL cleanup and primary-error preservation, and updated owning docs. All 22 targeted tests passed; changed-file Ruff and `git diff --check` passed. Initial sandbox attempts failed on pytest directory permissions before test execution; the same offline cases passed outside the sandbox. No full suite, repository-wide lint/type checks, CI/package workflows, benchmarks, review agents, live services, push, or GitHub thread changes.

Exact successful checks:

```powershell
poetry run pytest tests/test_database.py tests/test_execution.py::test_temporary_database_is_removed_after_success tests/test_execution.py::test_execution_stops_at_first_failing_statement tests/test_config.py::test_explicit_temporary_database_paths_are_rejected tests/test_config.py::test_temporary_override_clears_inherited_persistent_path tests/test_cli.py::test_cli_temporary_database_configuration -q -p no:cacheprovider --basetemp=.test-tmp-s03-verified --tb=short
poetry run ruff check --no-cache src/quackframe/config.py src/quackframe/database.py tests/test_database.py tests/test_execution.py tests/test_config.py tests/test_cli.py
git diff --check
```

### S04 Release recovery machinery

- [ ] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323304) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/scripts/release_workflow.py#L185) · [Local file](../scripts/release_workflow.py)
- Feedback: Decide whether draft retention, sealed hashes, tag reservations and PR-body metadata are needed for 0.1.0. Consider the documented stuck/retry states and rehearse remote publication steps.
- Decision: Pending discussion.
- Resolution / verification: Pending.

### S05 Separate flow work

- [x] Addressed — agreed separate PR
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323316) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/api.py#L14) · [Local file](../src/quackframe/api.py)
- Feedback: Keep quackframe_flow in its own PR; settle run parameters and a shared ordered job file list there. Address Prefect displaying sql_files as <tuple>.
- Decision: Agreed to handle flow, parameters and ordered job-list work in a separate PR.
- Resolution / verification: Deferred by agreement, not an unfinished implementation task for this PR. No completion or verification of that separate work is claimed here.

## Runtime and diagnostics

### R01 Useful SQL errors

- [x] Addressed — implemented on separate branch; integration pending
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323234) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/errors.py#L49) · [Local file](../src/quackframe/errors.py)
- Feedback: Restore actionable error details and file locations; correct statement attribution including PIVOT. Decide terminal versus external-log disclosure policy without exposing sensitive values.
- Decision: Implement a useful safe baseline from the practical DuckDB error
  investigation. Direct execution always shows full original errors; external
  runtimes show the safe baseline unless `allow_external_result_logging=true`,
  which permits full errors and selected results. Errors are reported either way;
  no extra setting. Ordinary identifiers are not treated as secrets merely
  because a caller could deliberately put a password in them.
- Resolution / verification: Complete on `refactor/error-logging`: `fbbcb71`
  implements useful diagnostics/source attribution; `e7652a9` fixes JSON-function
  diagnostics and locked-session configuration; `f8259ed` implements routing.
  The investigation recorded 42 scenarios in text/JSON modes (84 targeted
  probes); its consolidated report distinguishes ordinary exposure from
  deliberately constructed cases. Those counts are not a prevalence estimate.
  The doer/reviewer loop completed with no remaining actionable scoped findings.
  After review fixes, 41 error tests passed; final routing validation passed 79
  focused cases plus 11 selected CLI/mocked-Prefect cases. Independent review
  passed four offline checks. Changed-file checks passed except three documented
  pre-existing CLI-test lambda typing diagnostics. No full suite or live Prefect
  service was used. R06/R07 are not included.
  Remaining step: integrate the three commits into the feedback branch; neither
  integration nor push has occurred. Branch-only documents are
  `docs/duckdb-error-investigation.md` and
  `docs/epics/02-result-logging/02-useful-error-diagnostics.md`; read them in the
  logging worktree until integration. Some relation binder failures lack position
  metadata; candidate suggestions are omitted because they can contain PIVOT
  row values. Composite-key errors retain the first identifiable column.

### R02 Result logging executes the complete query

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323240) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/sql.py#L130) · [Local file](../src/quackframe/sql.py)
- Feedback: Ensure logged SELECTs execute every row exactly once. Add a counting-UDF regression above 10,240 rows for none, annotated and all logging.
- Decision: Execute each selected query completely once in DuckDB, then render
  a bounded native preview from its temporary result table.
- Resolution / verification: Implemented in `fix: fully execute logged SQL results`.
  DuckDB 1.5.5: 12 targeted tests passed, including a failure at row 25,000 of
  30,000 and one UDF call per row under none, annotation, and all logging.
  Native truncation and RETURNING regressions pass. Changed-file Ruff lint and
  format checks and `git diff --check` pass. See the
  [phase validation](../docs/epics/02-result-logging/01-sql-result-logging.md#validation)
  for the exact test command and validation limits.

### R03 NumPy dependency

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323250) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/pyproject.toml#L30) · [Local file](../pyproject.toml)
- Feedback: Make SQL functions work without the Prefect extra. Add a clean wheel smoke test enabling register_secret.
- Decision: Include NumPy in base dependencies and exercise a pure Python UDF in the clean wheel smoke test without Prefect.
- Resolution / verification: Moved NumPy out of the Prefect extra and dev group without upgrading locked packages. `poetry check --lock` and scoped `git diff --check` passed. Follow-up verification on 2026-10-14 passed: `poetry run python -m build --wheel --no-isolation`, then `poetry run python scripts/package_smoke.py dist/quackframe-0.1.0-py3-none-any.whl 0.1.0`. The clean Poetry environment installed NumPy without Prefect and successfully registered and called the Python UDF; the existing small public-entrypoint smoke checks also passed. Both commands exited 0. No full test suite ran.

### R04 Community extensions

- [x] Addressed — awaiting clarification
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323255) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/database.py#L157) · [Local file](../src/quackframe/database.py)
- Feedback: Choose repository-aware extension configuration or explicitly document core-only support and fix the mssql example.
- Decision: Awaiting Maitland's response to [Rowan's proposal](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4267371558), posted 2026-10-14.
  The proposal removes `duckdb.extensions` from TOML rather than adding
  repository-selection syntax: users can install/load extensions in SQL, and
  `register_secret` already loads its own requirements. Rowan asked whether
  there is a distinct use case that justifies retaining the TOML option.
- Resolution / verification: Comment verified on the PR. No implementation
  change made; implementation awaits discussion and is not on the active to-do list.

### R05 Read-only databases

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323259) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/sql_functions/installer.py#L55) · [Local file](../src/quackframe/sql_functions/installer.py)
- Feedback: Skip SQL-function installation when no functions are enabled. Provide a clear error for unsupported read-only installation.
- Decision: Skip installation entirely when no functions are enabled, including
  omitted configuration. Preserve enabled-function installation behaviour.
- Resolution / verification: Early return before registry resolution or DuckDB
  operations. Targeted regression checks cover caller transaction ownership,
  absence of the `quackframe` schema, and synthetic read-only execution with
  omitted and explicitly empty function configuration. Follow-up verification
  on 2026-10-14 passed all five selected cases (four deselected), including both
  read-only cases, using an accessible synthetic temporary directory outside
  the sandbox. Command: `poetry run pytest tests/test_sql_functions.py -k 'empty_installation or no_functions_permits_read_only_execution or registrar_supports_pure_connection_bound_and_optional_functions or unknown_enabled_function' -q -p no:cacheprovider --basetemp=.test-tmp-r05-verify-20261014 --tb=short`.
  No full test suite ran.

### R06 Progress logging

- [ ] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323264) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/engine.py#L46) · [Local file](../src/quackframe/engine.py)
- Feedback: Report file and statement start, completion, failure and elapsed time in the terminal and Prefect without logging SQL values.
- Decision: Pending discussion.
- Resolution / verification: Pending.

### R07 Result statement selection and annotations

- [ ] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323378) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/sql.py#L202) · [Local file](../src/quackframe/sql.py)
- Feedback: Review CALL, EXPLAIN ANALYZE and MERGE RETURNING support; fix trailing annotations attaching to the next statement.
- Decision: Pending discussion.
- Resolution / verification: Pending.

## Configuration and dependencies

### C01 Python database-path consistency

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323350) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/config.py#L291) · [Local file](../src/quackframe/config.py)
- Feedback: Make a path-only load_config call imply persistent mode consistently with CLI and environment input.
- Decision: Infer persistent mode when the Python invocation supplies a path but
  no mode. Override inherited database settings; keep explicit-mode validation.
- Resolution / verification: Implementation and configuration example updated.
  Added 13 regression cases for string/Path inputs, inherited source precedence,
  and incompatible explicit modes. All 26 selected configuration cases passed
  (21 deselected) with a fresh synthetic temporary directory outside the sandbox
  after sandbox filesystem permissions blocked fixture setup. No broader suite
  was run. `git diff --check` passed.

```powershell
poetry run pytest tests/test_config.py -k 'python_database_path or defaults_use_current_working_directory_and_memory or explicit_values_override_environment_dotenv_and_toml or boolean_and_path_conversion_match_environment_behavior or environment_database_fields_override_dotenv_as_one_source or memory_override_clears_a_toml_database_path or explicit_temporary_database_paths_are_rejected or temporary_override_clears_inherited_persistent_path' -q -p no:cacheprovider --basetemp=.test-tmp-c01-approved --tb=short
```

### C02 Relative configuration paths

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323359) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/config.py#L149) · [Local file](../src/quackframe/config.py)
- Feedback: Settle whether config_path resolves from the current directory or runtime root; align implementation and docs.
- Decision: Resolve relative configuration paths from the selected runtime root,
  including `QUACKFRAME_ROOT`; preserve absolute paths and default to
  `<runtime-root>/pyproject.toml` when `config_path` is omitted.
- Resolution / verification: Loader and runtime-root documentation updated.
  Eight regression cases cover competing same-named files in the working
  directory and runtime root, explicit-root precedence over the environment,
  environment-selected roots, string/Path inputs, absolute paths, and defaults.
  All 10 selected configuration cases passed (45 deselected) with a fresh
  synthetic temporary directory outside the sandbox after sandbox filesystem
  permissions blocked fixture setup. `git diff --check` passed. No broader
  checks ran.

```powershell
poetry run pytest tests/test_config.py -k 'configuration_paths_use_selected_runtime_root or defaults_use_current_working_directory_and_memory or missing_dotenv_preserves_current_behavior' -q -p no:cacheprovider --basetemp=.test-tmp-c02-approved --tb=short
```

### C03 Typed DuckDB settings

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323363) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/config.py#L81) · [Local file](../src/quackframe/config.py)
- Feedback: Accept plain TOML numbers and booleans and convert them appropriately for DuckDB.
- Decision: Accept strings, integers, floats, and booleans in the typed model; preserve strings, normalize booleans to `true`/`false`, and reject unsupported values.
- Resolution / verification: Added scalar pre-validation and documented ordinary TOML settings. `poetry run pytest tests/test_config.py -k duckdb_settings --basetemp .test-tmp-c03-20261014-c`: **19 passed, 55 deselected**. Includes unsupported compound/date values and an offline in-memory DuckDB connection. Sandbox directory permissions required escalation; an initial connection test used a session-only setting and was corrected to use a global option. Changed-file Ruff lint and `git diff --check` passed. Ruff formatted the new code; unrelated formatting changes were reverted. No broader checks ran.

### C04 Home-directory expansion

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323370) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/config.py#L118) · [Local file](../src/quackframe/config.py)
- Feedback: Expand ~ in database paths consistently with runtime-root handling.
- Decision: Expand the database path's leading `~` in the typed configuration
  before resolving relative paths against the runtime root.
- Resolution / verification: Implemented in the commit containing this entry
  (`fix: expand home directory in database paths`). All 15 targeted cases passed:
  nine home/relative/absolute path cases across typed, Python, and TOML inputs,
  five temporary-path rejection cases, and persistent retention after failure.
  Tests mock the home directory under the synthetic temporary directory.
  Sandbox directory permissions required escalation. `git diff --check` passed;
  no broader validation ran.

```powershell
poetry run pytest tests/test_config.py::test_database_paths_expand_home_before_resolving_runtime_root tests/test_config.py::test_temporary_database_rejects_home_path tests/test_config.py::test_explicit_temporary_database_paths_are_rejected tests/test_execution.py::test_execution_stops_at_first_failing_statement -q -p no:cacheprovider --basetemp=.test-tmp-c04-20261014-b --tb=short
```

### C05 TOML configuration authority

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323375) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/src/quackframe/config.py#L29) · [Local file](../src/quackframe/config.py)
- Feedback: Review rejection of root and project_name in [tool.quackframe], especially root changing after configuration sources were read.
- Decision: Reject `root` and `project_name` in `[tool.quackframe]` with clear
  source guidance. Establish root before reading configuration; preserve
  `[project].name`, typed fields, and existing invocation/environment contracts.
- Resolution / verification: Implemented in the commit containing this entry
  (`fix: reject runtime metadata in project TOML`). All 21 focused cases passed.
  Sandbox temporary-directory permissions required escalation for the same
  offline tests using fresh synthetic inputs. Changed-file Ruff lint and
  `git diff --check` passed. No broader checks ran.

```powershell
poetry run pytest tests/test_config.py::test_root_and_project_name_are_rejected_from_project_config tests/test_config.py::test_typed_config_accepts_root_and_project_name tests/test_config.py::test_project_name_is_loaded_for_runtime_display tests/test_config.py::test_configuration_paths_use_selected_runtime_root tests/test_config.py::test_defaults_use_current_working_directory_and_memory tests/test_config.py::test_dotenv_root_does_not_relocate_runtime_root tests/test_config.py::test_logging_controls_are_rejected_from_project_config tests/test_cli.py::test_cli_values_override_process_environment_and_dotenv -q -p no:cacheprovider --basetemp=.test-tmp-c05-20261014-b --tb=short
poetry run ruff check --no-cache src/quackframe/config.py tests/test_config.py tests/test_cli.py
git diff --check
```

### C06 DuckDB version constraint

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323383) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/pyproject.toml#L14) · [Local file](../pyproject.toml)
- Feedback: Consider a tested compatible range instead of an exact DuckDB patch pin.
- Decision: Accept `>=1.5.5,<1.6`, retaining DuckDB 1.5.5 in the Poetry lock.
- Resolution / verification: Updated the dependency constraint and two active
  documentation statements about the exact pin. `poetry lock` changed only the
  lock content hash; no locked dependencies were upgraded. `poetry check --lock`
  passed with the existing license-table deprecation warning; `git diff --check`
  passed. Historical tested-version evidence remains unchanged. No runtime tests
  or broad checks ran, and compatibility across all allowed patches is not claimed.

### C07 Calendar-version dependency caps

- [x] Addressed — awaiting clarification
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323392) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/pyproject.toml#L21) · [Local file](../pyproject.toml)
- Feedback: Review annual upper bounds on Azure dependencies and fsspec; avoid arbitrary January incompatibility.
- Decision: Awaiting Maitland's clarification. Azure fsspec removal leaves only
  the SFTP fsspec dependency in scope. On 2026-10-14, Rowan posted a reply asking
  whether to remove the upper bound entirely or use a different bounded range.
  [Clarification comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4266977546).
- Resolution / verification: Pending response; the dependency constraint remains
  unchanged. Addressed by requesting clarification; no implementation action until a response.

## Validation and repository cleanup

### V01 Linux and package CI

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323271) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/.github/workflows/ci.yml#L27) · [Local file](../.github/workflows/ci.yml)
- Feedback: Add Linux coverage, plus package build, twine check and clean wheel smoke tests on PRs.
- Decision: Implement together with O02, preserving the existing Windows cases.
- Resolution / verification: Added full-extras Linux Python 3.11/3.14 cases and
  a separate Linux Python 3.14 PR package job using the existing build, Twine
  and clean-wheel smoke tooling. Publication workflow and smoke script unchanged.
  Targeted YAML/configuration validation passed (matrix, supported versions, PR
  triggers, package command order, metadata version and read-only permissions).
  The existing release workflow safety test passed (one test; pytest reported
  a non-fatal cache-write permission warning). Documentation links and
  `git diff --check` passed in the initial configuration check.
  Follow-up on 2026-10-16: clean-wheel consumer checks passed on Windows/Python
  3.14.0 and Ubuntu WSL/Python 3.11.14. Each verified installation without
  Prefect, Python UDF execution, shared-session Python/CLI execution and
  fail-fast behavior. Both resolved DuckDB 1.5.6 and NumPy 2.4.6 from the wheel's
  allowed dependency ranges; these were consumer checks, not locked full-suite
  runs. WSL's installed Poetry 1.8.2 could not parse current wheel metadata;
  a disposable Poetry 2.2.1 environment completed the Linux checks without
  changing installed tools. The V03-built sdist and wheel also passed Twine.
  Hosted matrix execution, Linux/Python 3.14 and optional-extras coverage remain
  pending. No full suite, hosted workflow or publication was triggered.

### V02 Opt-in upstream deadlock controls

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323301) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/tests/test_sftp_integration.py#L498) · [Local file](../tests/test_sftp_integration.py)
- Feedback: Move four deliberately timing-out upstream SFTP controls behind an opt-in marker; retain Quackframe serialization coverage.
- Decision: Retain all four controls, excluded by default with the registered
  `upstream_sftp_control` marker; explicitly opt in with `-m upstream_sftp_control`.
- Resolution / verification: Updated pytest defaults and marked only the
  Paramiko/fsspec four-thread parameter combinations (traced and untraced).
  [Contributing](../CONTRIBUTING.md) documents the opt-in command. Collection-only
  checks selected 47/51 SFTP cases by default (exactly four deselected), and 4/51
  with opt-in (the exact four controls). Expected-failure classification, tracing,
  runtime code and protected tests are unchanged. Changed-file Ruff lint/format,
  documentation links and `git diff --check` passed. No test bodies were executed.

### V03 Public repository cleanup

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323278) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/.gitmodules#L1)
- Feedback: Review unused submodules/gitlinks; remove completed working notes; fix stale prototype references, private links and supplier-specific test paths; trim sdist contents; refresh PR validation figures.
- Decision: Complete the public-repository cleanup; retain useful historical
  prototype evidence without requiring private source access.
- Resolution / verification: Submodule configuration/gitlinks and stale agent
  map entry removed in `67d279b` and `2aa2c02`. Removed completed `found-bugs.md`
  and implementation-review notes, the private Azure DevOps reference, and
  supplier-specific test paths. Clarified that prototype references describe
  historical local development material. Trimmed the sdist to source, README,
  licence and project metadata; Hatchling also includes its `.gitignore` and
  generated `PKG-INFO`. Built the wheel from that sdist and checked both archive
  inventories: 49 files each, no tests/scripts/docs/examples/Poetry lock.
  Four affected scope-override cases passed; changed-file Ruff, Poetry lock
  consistency, documentation links and diff checks passed. Build temporary-file
  access required normal sandbox escalation. No full suite or publication ran.
  Updated PR #2's validation paragraph to the review's recorded 628 passed /
  4 xfailed at `a7ab179`, explicitly separating subsequent targeted branch
  verification from the unmodified PR head. No new full-suite total is claimed.

### V04 Credential documentation table

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323403) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/docs/credential-providers.md#L128) · [Local file](../docs/credential-providers.md)
- Feedback: Remove the stray three-column row in the two-column table.
- Decision: Remove the misplaced credential-shape row from the override table.
- Resolution / verification: Removed only the stray row; retained the valid
  `azure_managed_identity` scope override. Documentation link check and
  `git diff --check` passed. No runtime checks ran.

## Before enabling releases

### P01 PyPI verification delay

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323325) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/scripts/release_artifacts.py#L133) · [Local file](../scripts/release_artifacts.py)
- Feedback: Poll publication verification long enough to tolerate cached 404 responses after upload.
- Decision: Approved bounded polling for verification only: every 20 seconds
  for three minutes, allowing several cycles of the roughly one-minute cached
  404 measured in the review. An in-flight request retains its 30-second timeout.
- Resolution / verification: Verification waits for missing files, preserves
  exact file/hash checks, and reports remaining filenames on timeout. Staging
  and upload behavior are unchanged. Eight focused mocked-response/fake-clock
  cases passed, covering delayed 404/partial visibility, timeout, conflicting
  hashes, unexpected files, HTTP/network/JSON errors and local checksum failure.
  Command: `poetry run pytest tests/test_release_artifacts.py -k pypi_verification_polling -q -p no:cacheprovider --basetemp=.test-tmp-p01-elevated --tb=short`.
  The initial sandbox run could not access temporary fixtures; the approved
  elevated rerun passed. No live requests, real waits or publication occurred.
  Changed-file Ruff lint/format checks, Pyright (with elevated environment
  access after sandbox import-resolution failures), and `git diff --check`
  passed. No full release or repository suite was run.

### P02 Trusted release execution

- [ ] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323333) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/.github/workflows/release.yml#L136) · [Local file](../.github/workflows/release.yml)
- Feedback: Separate candidate code from privileged release tooling; review main-only environment restrictions and App-key secret placement.
- Decision: Approved default-branch tooling and policy, a separate unprivileged
  candidate build job, and `main`-only `pypi` environment protection with the App
  key stored only as an environment secret.
- Resolution / verification: Repository implementation complete. Planning and
  privileged jobs use the workflow's immutable default-branch SHA; isolated Python
  excludes candidate import paths. Retention/finalization consume the planner's
  full decision through job outputs and reject substituted build metadata.
  Seventeen focused offline cases passed for import/policy isolation, forged
  decisions, patch provenance, retries, finalization and workflow boundaries.
  Seven focused P04/P05 history controls also passed, preserving collided-candidate
  protection and ordinary pre-stable `main` no-release behavior.
  Changed-file Ruff lint/format, Pyright, YAML parsing and doc links passed.
  Pytest fixture access and Pyright dependency resolution needed normal sandbox
  escalation. No builds, full suites, hosted runs or publication were performed.
- External setup remains unverified, so this item stays open: the available
  GitHub connector has no environment administration operation and local `gh`
  is unavailable. An owner must set `pypi` deployment rules to the `main` branch
  only, supply `QUACKFRAME_RELEASE_APP_PRIVATE_KEY` as an environment secret from
  their secure original, verify that replacement, then remove any repository or
  broadly scoped organization copy. No secret was read or external setting changed.

  Focused test command:

  ```powershell
  poetry run pytest tests/test_release_workflow.py -k 'trusted or candidate_build or retry_upload_and_finalization or new_release_finalizes or workflow_serializes or patch_provenance' -q -p no:cacheprovider --basetemp=.test-tmp-p02-b --tb=short
  poetry run pytest tests/test_release.py -k 'collided_patch_candidate or main_before_first_stable_without_promotion' -q -p no:cacheprovider --basetemp=.test-tmp-p02-controls --tb=short
  ```

### P03 Workflow hardening

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323339) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/.github/workflows/release.yml#L35) · [Local file](../.github/workflows/release.yml)
- Feedback: Scope write tokens to required steps, pin privileged actions to commit SHAs and set job timeouts.
- Decision: Approved. Preserve P02's job isolation, scope planning's token
  environment to API steps, pin the two privileged actions and bound all release
  jobs. GitHub token permissions remain job-level; no step permissions added.
- Resolution / verification: Planning exposes `GH_TOKEN` only to plan/authorize;
  App tokens remain limited to retain/finalize steps. Timeouts are 15/30/10/15/10
  minutes for plan/package/retain/publish/finalize. On 2026-10-15, read-only
  `git ls-remote` against the authoritative upstream repositories verified
  `actions/create-github-app-token` v3 and v3.3.0 at
  `64ab729a6294000f5aa4a4bc0b73d1f32bc45510`, and
  `pypa/gh-action-pypi-publish` release/v1 and peeled v1.14.2 at
  `dc37677b2e1c63e2034f94d8a5b11f265b73ba33`. These exact commits are pinned;
  unrelated action versions are unchanged. Focused pytest selection
  `workflow_serializes or candidate_build_is_separate or limits_token_exposure or verified_commit_pins`
  in `tests/test_release_workflow.py`: **4 passed, 59 deselected**. Changed-file
  Ruff lint/format and Pyright, documentation links and `git diff --check` passed.
  Upstream reads and Pyright required normal sandbox escalation; Pyright then
  caught a missing test set annotation, corrected before the passing rerun.
  Actionlint was unavailable on PATH. No hosted workflows, builds, publication
  or broad test suite ran. P02 external setup remains unverified.

### P04 RC and patch ancestry

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323346) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/scripts/release.py#L167) · [Local file](../scripts/release.py)
- Feedback: Prevent direct patches taking an RC target version and later shipping candidate changes as an unrelated patch; add the four-step history regression.
- Decision: Approved. Detect uncovered reachable RC ancestry independently of
  target version; apply the version filter only when selecting a valid RC.
  Preserve direct patches and require a refreshed candidate after a collision.
- Resolution / verification: Separated ancestry detection from candidate version
  selection. The four-step synthetic history failed before the fix and passes
  after it, including rejection with explicit patch provenance and automatic
  planning, refreshed-candidate recovery, and direct patches after promotion.
  The focused run passed 26 cases (62 deselected), including concurrent minor
  candidates, promotion freshness, retries and pre-stable P05 controls.
  Changed-file Ruff lint/format, Pyright, documentation links and diff checks
  passed. Fixture access and Pyright dependency resolution required normal
  sandbox escalation. No full suites, builds, hosted execution or publication.

  Targeted test command:

  ```powershell
  poetry run pytest tests/test_release.py -k 'collided_patch_candidate or candidate_promotion_patch_and_concurrent_next_minor or promotion_target_and_freshness or retry_resumes_original_version or main_before_first_stable_without_promotion or first_stable_explicit_promotion' -q -p no:cacheprovider --basetemp=.test-tmp-p04-verified --tb=short
  ```

### P05 Before the first stable release

- [x] Addressed
- Source: [GitHub comment](https://github.com/maitdevptyltd/quackframe/pull/2#discussion_r4213323399) · [Reviewed code](https://github.com/maitdevptyltd/quackframe/blob/a7ab17974d25a5c9289fbacef22db4a9144e9324/scripts/release.py#L205) · [Local file](../scripts/release.py)
- Feedback: Return no release for ordinary main pushes before initial promotion instead of failing the release run.
- Decision: Return no release before stable exists when main has neither a
  reachable RC nor an explicit promotion request; preserve promotion validation.
- Resolution / verification: Added the narrow planner guard and documented the
  no-release outcome. Synthetic local Git histories cover ordinary feature, fix
  and breaking pushes, with and without an unmerged RC, plus invalid explicit
  promotions. Before the fix: six regressions failed and two controls passed.
  After the fix: 16 targeted cases passed, 71 deselected, including first stable
  promotion, candidate tree/selection validation, bootstrap conflicts and
  post-stable feature rejection. Fixture permissions required normal escalation;
  changed-file Pyright also required escalation to resolve installed dependencies.
  Changed-file Ruff lint/format, Pyright, documentation links and diff checks
  passed. No full release/repository suite, builds, hosted workflows or publishing.

  Exact targeted verification:

  ```powershell
  poetry run pytest tests/test_release.py -k 'main_before_first_stable_without_promotion or first_stable_explicit_promotion or bootstrap_through_second_candidate_and_stable or promotion_requires_exact_candidate_tree or selected_candidate_is_not_silently_substituted or direct_feature_on_main_is_rejected or bootstrap_rejects_conflicting_tag_history' -q -p no:cacheprovider --basetemp=.test-tmp-p05-verified --tb=short
  poetry run ruff check scripts/release.py tests/test_release.py
  poetry run ruff format --check scripts/release.py tests/test_release.py
  poetry run pyright scripts/release.py tests/test_release.py
  poetry run python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
  git diff --check
  ```

## Overview-only actions

Source for each: [Maitland's overview](https://github.com/maitdevptyltd/quackframe/pull/2#pullrequestreview-5449915627).

- [x] O01 — Include scripts in CONTRIBUTING.md lint commands to match CI.
  Decision / resolution: Added `scripts` to both Ruff commands in
  [Contributing](../CONTRIBUTING.md) and verified they match
  [CI](../.github/workflows/ci.yml). Documentation link check and
  `git diff --check` passed. The documented lint commands were not executed.
- [x] O02 — Reconcile advertised Python 3.14 support with CI coverage.
  Decision / resolution: Added full-extras Python 3.14 tests on Windows and
  Linux, plus Linux Python 3.14 clean-wheel coverage without extras. Preserved
  Windows core-only 3.11/3.13 and minimum-Prefect coverage. Seven explicit test
  cases avoid a Cartesian matrix. Targeted configuration validation passed;
  hosted Python 3.14/Linux execution is pending, as detailed in
  [V01](#v01-linux-and-package-ci). [CI](../.github/workflows/ci.yml) · [Package metadata](../pyproject.toml)
- [x] O03 — Use a monotonic high-resolution timer such as time.perf_counter()
  for elapsed durations. Decision / resolution: File and run durations now use
  `perf_counter()` and retain their public `timedelta` types. No stored wall-clock
  timestamps existed to change. Controlled-clock regressions cover forward and
  backward wall-clock jumps; both cases plus ordering, fail-fast and temporary
  cleanup passed (five tests). Changed-file Ruff lint/format checks, documentation
  links and `git diff --check` passed. [SQL execution](../src/quackframe/sql.py) ·
  [Run execution](../src/quackframe/engine.py)
- [x] O04 — Keep subsequent PRs small enough for meaningful review.
  Decision / resolution: Accepted guidance for future PRs, not an outstanding
  code change or additional review point to implement in this PR.

## Related Docs

- [Configuration](../docs/configuration.md): database modes and settings.
- [Filesystems](../docs/filesystems.md): filesystem routes and ownership.
- [Credential providers](../docs/credential-providers.md): shared credential contracts.
- [Release guide](../docs/releases.md): publication and activation.

