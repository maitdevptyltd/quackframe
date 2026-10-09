# Prefect Deployment Entry Point

Status: **In Progress**
Last updated: 2026-10-07
Epic: 06 Prefect Deployment
Phase: 01
Related docs: [Runtime Adapters](../../runtime-adapters.md), [Developer API](../../developer-api.md), [Configuration](../../configuration.md)

## Developer API

`quackframe_flow` is exposed from the optional Prefect runtime integration. It is
a real Prefect flow, so developers use Prefect's existing deployment methods
directly. Quackframe does not implement or wrap `.deploy()`.

The following example registers a deployment using an image that the consuming
project has already built and published.

Configure the existing `QUACKFRAME_ROOT` environment variable in the process
or container that will execute the flow:

```text
QUACKFRAME_ROOT=/app
```

This sets the base filesystem directory for SQL file paths and Quackframe
configuration. Supply it through the deployment infrastructure's environment
settings, not through flow parameters. Setting it only on the machine that
registers the deployment does not configure the remote execution environment.

```python
from prefect.types.entrypoint import EntrypointType

from quackframe.integrations.prefect import quackframe_flow


if __name__ == "__main__":
    quackframe_flow.deploy(
        name="daily-reporting",
        work_pool_name="analytics",
        image="your-registry/reporting:1.0.0",
        build=False,
        push=False,
        entrypoint_type=EntrypointType.MODULE_PATH,
        parameters={
            "sql_files": [
                "sql/prepare.sql",
                "sql/report.sql",
            ],
        },
    )
```

`name` identifies the Prefect deployment. No additional flow wrapper, flow
factory, or flow renaming is required. The Python callable is named
`quackframe_flow` because it represents Quackframe's execution contract. Its
default Prefect flow name remains `quackframe-run`.

`sql_files` is mandatory. Files execute sequentially in exactly the supplied
order: `prepare.sql` completes before `report.sql` starts, using the same
DuckDB session. If a file fails, later files do not run. Quackframe does not
sort paths or infer execution order from their names.

Optional public inputs `config_path` and `config` allow a deployment or Python
caller to select alternative configuration. Most deployments omit both and
use the project configuration and execution environment described below.

The module entry point allows Prefect to import the installed package in the
execution environment instead of depending on the deployment author's local
Python installation path. The work pool must support the chosen image and
have its normal execution infrastructure configured. These are native
[Prefect deployment options](https://reference.prefect.io/prefect/flows/).

Developers can also call the flow without creating a deployment. Set
`QUACKFRAME_ROOT` to the local project directory in that process's environment:

```python
from quackframe.integrations.prefect import quackframe_flow

result = quackframe_flow(
    sql_files=["sql/prepare.sql", "sql/report.sql"],
)
```

### SQL Files In The Execution Environment

For the deployment above, the running container has `QUACKFRAME_ROOT=/app`
and must contain:

```text
/app/
    pyproject.toml
    sql/
        prepare.sql
        report.sql
```

It must also have compatible versions of `quackframe[prefect]` and the
project's other dependencies installed. The deployment process needs the
optional integration installed to import and register the flow.

Passing paths does not upload files. Quackframe reads these files when the
flow runs, in the environment executing the flow. `/app` is an example
container path, not a prescribed repository layout. A path on the deployment
author's computer is not automatically available to the worker.

The consuming project owns delivery of its SQL, project configuration, and
dependencies. The primary example will use a prebuilt image containing them.
A mounted directory or a checkout prepared by the deployment infrastructure
can also supply files, provided they exist before the flow starts. Prefect
owns its [code retrieval mechanisms](https://docs.prefect.io/v3/how-to-guides/deployments/store-flow-code);
Quackframe will not add a download, repository-cloning, or packaging service.

Relative SQL paths resolve against the runtime root; absolute paths refer to
the execution environment. The deployment flow reads `QUACKFRAME_ROOT` from
its process environment, falling back to the process working directory when
unset. Deployment examples should set the environment variable explicitly.
It must be available before configuration discovery; putting it in the
runtime-root `.env` cannot establish the root needed to find that file.
The flow does not expose a `root` parameter. Do not change the
process working directory or assume that SQL-internal relative data paths
use the same root; those retain existing DuckDB behaviour.

## Purpose And Boundaries

Make the existing optional Prefect runtime directly deployable using ordinary
file paths. Deployment is one way to invoke Quackframe, not its required
execution model. CLI, F5, direct Python execution, and other schedulers remain
first-class paths.

Quackframe owns configuration resolution, file preparation, ordered execution,
one shared DuckDB session, SQL extensions, cleanup, results, and its Prefect
flow/task representation. Prefect owns deployment registration, schedules,
work pools, infrastructure, and launching runs. The consuming project owns
SQL, dependency versions, deployment settings, and credential provisioning.

## Flow Input Contract

The typed flow body has this signature; decorating it produces the
public Prefect flow object:

```python
def quackframe_flow(
    sql_files: list[str],
    *,
    config_path: str | None = None,
    config: QuackframeConfig | None = None,
) -> ExecutionResult:
    ...
```

- `sql_files` is mandatory and must be a non-empty list of paths. Execute
  files sequentially in their received order in one shared DuckDB session.
  Stop on the first failure. No sorting, parallel file execution, globbing,
  directory discovery, or inferred ordering is introduced.
- By default, the base directory is configured with `QUACKFRAME_ROOT` in the
  execution environment; there is no separate `root` flow parameter.
- `config_path` is an optional public input selecting an alternative TOML
  configuration file in the execution environment. It replaces the default
  `pyproject.toml` file as the project configuration source; it is not an
  additional file layered over that default. Use the existing
  `[tool.quackframe]` structure and configuration loader. Relative explicit
  configuration paths resolve from the process working directory, matching
  `load_config()`; SQL paths continue to resolve from the runtime root.
  Runtime-root `.env`
  and process environment settings retain their normal precedence. If omitted,
  discover `pyproject.toml` under the runtime root as today.
- Ordinary deployments pass paths and load configuration at run time from
  project TOML, runtime-root `.env`, and the process environment. Calling this
  flow explicitly selects `runtime="prefect"`, overriding the runtime setting
  in those sources without modifying them.
- `config` is an optional public input supplying a complete, typed
  `QuackframeConfig`. It preserves the existing resolved Python configuration path,
  including calls from `quackframe.run(..., config=...)`. It bypasses source
  loading and cannot be combined with `config_path`. Require its
  runtime to be `prefect`; reject a conflicting configuration explicitly.
  Retain project-name metadata for local adapter calls.
- A supplied `config` is a complete replacement, not a partial patch merged
  into project TOML or environment settings. It can therefore also supply the
  root through `config.root`. This deliberate configuration override is
  supported; ordinary deployments should use `QUACKFRAME_ROOT` and omit
  `config`. Any paths in supplied configuration must refer to the execution
  environment. Credentials remain in native secure providers or injected
  environment settings, outside deployment parameters.
- Deployment parameters must pass Prefect's native schema generation and
  JSON round-trip validation. No DuckDB connections, parsed statements, or
  `PreparedSqlFile` objects cross that boundary.

## Implementation Shape

Previously `run()` resolved configuration and prepared SQL before selecting the
runtime implementation. The internal flow therefore received parsed DuckDB
statement objects. Simply exporting it would not meet this path-based
deployment contract.

One public decorated `quackframe_flow` now lives in the Prefect integration
and is exported from `quackframe.integrations.prefect`. It replaces the old
internal decorated flow without nesting or retaining a superseded alias.

1. The internal runtime dispatch boundary accepts ordered file paths
   and resolved configuration. The public `run(sql_files, config=...)`
   signature is unchanged, including its support for iterables and `Path` values.
   The caller's iterable is materialized once.
2. File preparation and external-result permission validation live in
   `runtimes/preparation.py`, shared by runtime entry points. It reads
   the registry's result-log policy without Prefect-specific branches in
   core configuration or CLI code.
3. `runtimes/direct.py` provides a thin entry function that prepares files and
   calls the existing prepared-plan engine. `execute_plan` remains responsible
   for session ownership and execution, with its prepared-file contract intact.
4. The Prefect adapter invokes the public flow using path strings and the
   already resolved configuration. The deployed flow instead loads that
   configuration on the worker using `QUACKFRAME_ROOT` when no `config` is
   supplied. Existing explicit-root configuration through the CLI and Python
   API remains unchanged; this feature adds no flow-level root parameter.
5. The public flow prepares and validates all files once, then invokes
   the existing engine using the current filename-named task executor. It does
   not call public `run()`, which would select Prefect again.

This creates one Quackframe flow per invocation and one task per SQL file.
Configuration loading for deployments happens inside the flow; ordinary
`run()` still resolves configuration before runtime selection. Preparation
errors on the Prefect path are now visible as failed flow runs, while
still occurring before a DuckDB session opens or project SQL executes.

Preserve no retries, no caching, no persisted results, serial execution,
fail-fast behaviour, shared-session ownership, and cleanup. Preserve
`QuackframeError` identity and existing CLI exit statuses through the adapter.
Selected result logging must retain its permission gate and single retention
warning. Native Prefect validation errors remain Prefect-owned; execution
errors raised by Quackframe retain Quackframe's safe diagnostics.

Project-derived flow-run naming includes configuration loaded inside deployed
runs. A run-specific Prefect client update sets the name after configuration
loading without mutating the shared flow object. Explicit native
`flow_run_name` customisation takes precedence over this default.

Base-package imports must not load Prefect. Importing the explicit Prefect
integration may load its dependency, and must give an actionable
`quackframe[prefect]` installation error when unavailable. Keep credential
provider imports independent of runtime activation.

## Implementation Sequence

- [x] Verify module-entry-point deployment, parameter schema generation, and
  flow-run naming against the supported Prefect range (`>=3.2,<4`). Record the
  tested versions. If this requires a new minimum, bring that compatibility
  decision back for review rather than silently narrowing support.
- [x] Refactor internal runtime dispatch and shared preparation with regression
  coverage for direct execution and existing Prefect behaviour.
- [x] Expose `quackframe_flow`, remove the superseded internal flow, and prove
  package entry-point loading from a fresh process.
- [x] Add a neutral deployment example under `examples/prefect/`, showing the
  prebuilt-image contract, `QUACKFRAME_ROOT` in the execution environment,
  execution-time paths, and project configuration.
  Use Poetry for dependency and environment management.
- [x] Update developer API, runtime, configuration, and example documentation
  to describe implemented behaviour. Update this phase's status and evidence.

## Acceptance And Validation

- A developer imports the public flow and uses native `.deploy()` without
  writing a wrapper. Register and inspect a deployment against an isolated
  Prefect test server; verify its importable module entry point and JSON
  parameters rather than only mocking `.deploy()`.
- A fresh execution process can import the flow from an installed package and
  load SQL using its own `QUACKFRAME_ROOT`, even when its working directory
  differs from that root. No author-machine paths or parsed objects are
  required. Prove the working-directory fallback when the variable is unset
  and verify that the public flow schema has no `root` parameter.
- A deployment-triggered smoke run using the example image produces one flow
  and two tasks. The second SQL file observes session state created by the
  first. Record this separately from local and metadata tests; if container
  infrastructure is unavailable, report that verification as outstanding.
- Missing, empty, malformed, or unreadable SQL inputs fail before opening the
  DuckDB session. Configuration precedence, default root, conflicting inputs,
  and missing optional dependencies have focused coverage.
- Verify that omitted or empty `sql_files` is rejected, and that an intentionally
  non-alphabetical file list executes in supplied order. Cover both optional
  configuration inputs: alternate-file loading with normal environment
  precedence, complete-object replacement, and rejection when both are supplied.
- Prove ordering, failure short-circuiting, cleanup, result semantics, result
  logging permission, error identity, CLI statuses, and project run naming.
- Prove base-package operation without Prefect and unchanged direct/CLI/F5
  contracts. No new deployment-specific core dependency is introduced.

During implementation, run focused tests first, then the repository checks:

```powershell
poetry run pytest
poetry run ruff check .
poetry run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

## Validation Evidence

- Implementation, developer documentation, and automated validation are
  complete. The phase remains **In Progress** pending the container smoke run
  below; no further API or runtime work is currently identified.
- Prefect 3.8.6 / Python 3.13 on Windows: the full repository suite finished
  with **611 passed and 4 expected failures** in the existing unprotected SFTP
  diagnostic controls. The completed invocation used
  `poetry run python -u -m pytest -vv --tb=short -o faulthandler_timeout=60`
  to retain per-test progress and timeout diagnostics after an earlier quiet
  full-suite attempt was interrupted without a result.
- `poetry run pyright`: **0 errors, 0 warnings**. Maintained code passes
  `poetry run ruff check src tests scripts examples`, and touched Python files
  pass Ruff's format check. The standard `poetry run ruff check .` reports
  **13 existing findings** confined to the untouched `MAD.Utilities.DuckDB/`
  prototype; these were not changed as part of this feature.
- Documentation link/anchor validation, terminology review, and
  `git diff --check` pass.
- The deployment regression registers through native `.deploy()` against an
  isolated Prefect server, inspects the recorded module entry point and JSON
  parameters, creates a run from that deployment, and executes it through
  `prefect.engine` in a fresh process. It verifies two file tasks, shared
  temporary-table state, the resulting persistent data, and the project run
  name. The worker's root differs from its working directory.
- Prefect 3.2.0 compatibility: 41 tests passed and one optional SFTP-dependent
  test skipped, using a non-editable Quackframe package installed through a
  disposable Poetry project. This also verifies minimum-version module
  deployment and configuration schema support. No minimum-version change was
  needed.
- The disposable 3.2.0 environment used FastAPI 0.115.12 after the latest
  unconstrained FastAPI caused Prefect's own server to fail before flow
  execution. Prefect/Pydantic deprecation warnings remain upstream. The
  repository dependency declarations and lock file were not changed.
- Container smoke execution remains unverified: Docker Desktop's engine was
  unavailable. The fresh-process deployment regression verifies Quackframe's
  deployment loading and SQL behaviour, but does not establish image contents,
  registry access, or a live work pool's container launch configuration.

## Outside This Scope

No Quackframe deployment command or deployment abstraction, image builder,
artifact uploader, scheduler, infrastructure provisioning, job manifest,
remote SQL-path protocol, or automatic file discovery. No changes to the core
SQL execution guarantees or requirement to deploy through Prefect.

The developer-facing contract is documented in the
[public flow API](../../developer-api.md#prefect-flow). The implementation
preserves the scope approved for this phase.

## Related Docs

- [Overview](../../overview.md): Quackframe's purpose and product boundaries.
- [Runtime Adapters](../../runtime-adapters.md): existing runtime guarantees.
- [Developer API](../../developer-api.md): current public execution API.
- [Configuration](../../configuration.md): root and configuration authority.
- [Prefect Example](../../../examples/prefect/README.md): current local usage.
- [Original Prefect Phase](../01-mvp/06-prefect-runtime.md): implemented adapter.
- [Roadmap](../../roadmap.md): delivered and planned work.
