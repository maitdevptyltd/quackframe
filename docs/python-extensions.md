# SQL Function Extensions

Quackframe can expose self-contained Python capabilities to SQL. Each function
is an independent unit of work that conforms to a small installation contract
without being forced into shared thematic implementation.

The base installation includes NumPy for DuckDB's Python UDF registration;
SQL functions require the Prefect extra only when using a Prefect capability.

## Public Naming

Downstream SQL uses a schema-qualified name:

```sql
SELECT quackframe.function_name(...);
```

DuckDB's Python `create_function()` treats a dotted name as a literal function
name rather than normal schema qualification. Quackframe therefore registers a
private Python UDF and creates a public SQL macro:

```text
Python UDF:  _quackframe_function_name
Public SQL:  quackframe.function_name
```

For example:

```sql
CREATE SCHEMA IF NOT EXISTS quackframe;

CREATE OR REPLACE MACRO quackframe.register_secret(
    provider,
    reference,
    secret_type,
    alias := NULL,
    overrides := NULL
) AS _quackframe_register_secret(
    provider,
    reference,
    secret_type,
    alias,
    overrides
);
```

The `quackframe` schema is reserved for Quackframe-managed macros and any
future metadata contract. Project SQL should not create unrelated objects in
that schema.

## Function-owned Packages

Each non-trivial function owns its vertical implementation slice:

```text
credential_loading/
    loading.py
    models.py
    validation.py
    providers/
sql_functions/
    definition.py
    registry.py
    installer.py
    validation.py
    register_secret/
        __init__.py
        function.py
        models.py
    register_filesystem/
        __init__.py
        function.py
        models.py
```

A simple function may begin as one module. When its supporting logic grows, it
becomes a function-named package. Themes such as credentials or observability
may be recorded as metadata and documentation categories; they do not force
unrelated functions into a shared implementation hierarchy.

Limited duplication is preferable to restrictive coupling. Shared code should
be extracted only when the behaviour and invariant genuinely have one owner and
must change together. The secret and filesystem functions share credential
loading, fields, validation and overrides. Each retains its own SQL wrapper
and operation-specific registration strategies.

## Minimal Function Contract

A function definition needs enough metadata for deterministic registration:

```python
function = SqlFunction(
    name="register_secret",
    callable=register_secret,
    bind_connection=True,
    side_effects=True,
)
```

The eventual contract should describe:

- public and private names;
- the Python callable;
- argument and return types;
- optional-argument macro behaviour;
- null handling and side effects;
- required DuckDB extensions;
- optional Python dependencies;
- safe diagnostic metadata.

The registrar inspects the callable signature rather than requiring every
function package to repeat its parameters manually. Supported type annotations
describe the DuckDB-callable arguments and return value. Unsupported signatures
fail during installation, before project SQL begins.

When `bind_connection` is true, the callable's first parameter receives the
active `DuckDBPyConnection`. The registrar removes that parameter from the
SQL-visible signature and binds the connection before passing the callable to
DuckDB. The prototype demonstrates this cleanly with `functools.partial`;
Quackframe retains the binding behaviour without making that helper part of the
public API.

Optional parameters supported by Quackframe are translated into defaults on
the public macro. The private Python UDF remains fixed-arity, as required by
DuckDB. Unsupported default values, keyword-only parameters, and variadic
parameters fail with a definition error unless Quackframe deliberately adds a
mapping for them.

Functions must use unique public names, register deterministically, avoid
mutating another function's private state, and follow Quackframe's error and
data-safety rules. They do not need common models, providers, or internal base
classes beyond that boundary.

## Function-neutral Boundary

The execution runner opens the DuckDB connection and asks one installer to
register the enabled definitions. It does not know which functions exist, how
they obtain credentials, or whether they need a connection. The registrar
handles only descriptor validation, callable binding, DuckDB registration, and
public macro creation.

Adding a function may add its descriptor to the built-in registry, but it must
not add a function-name branch or function-specific request queue to the runner
or registrar. Function-specific models, strategies, and lifecycle decisions
remain inside the function package.

## Registration

Before project SQL executes, Quackframe:

1. resolves the enabled function definitions;
2. validates unique names, signatures, and function-wide optional dependencies;
3. registers each private Python UDF on the active connection;
4. creates or replaces its public macro in the `quackframe` schema; and
5. reports enabled public names without exposing sensitive configuration.

MVP built-ins belong to one explicit, reviewable registry. The registrar loops
over that collection; it does not discover built-ins by scanning modules or
directories. This makes registration order, optional imports, and the SQL
capability surface deterministic.

Discovery, enablement, and registration remain separate concepts. External
packages may later advertise definitions through Python package entry points,
but discovery would only make them available. A separate allowlist must enable
them before the same generic registrar exposes them to SQL. External discovery
is not required for the MVP.

An optional dependency that belongs to a choice made inside a function is
loaded at that narrower boundary. For example, enabling `register_secret` does
not require Prefect; selecting its `prefect` credential provider does. This
allows other providers to remain independent while the generic function
registrar stays neutral.

## Connection-aware Mutation

A Python UDF that changes the same DuckDB instance may be unable to issue that
change through the connection currently executing the UDF. The prototype avoids
a runner-owned request queue by opening a short-lived duplicate connection to
the same database instance inside the connection-aware function.

`register_secret` uses a short-lived duplicate connection. Resource-aware functions
such as `register_filesystem` declare `bind_resources=True`: their first Python
argument is a `SessionResources` owner containing the root connection. The
installer injects this owner outside the SQL signature; ordinary connection-bound
and pure functions retain their existing contracts. Binding modes are exclusive.

The runner supplies one resource owner per session and closes it after SQL work,
before closing the root connection. Callers installing resource-aware functions
manually must supply an explicit owner and keep its root connection alive.
Filesystem registration retains root-derived duplicate handles until cleanup,
then unregisters backends and closes their clients and handles. The core runner
has no deferred-operation queue or function-specific branch. Compatibility has
been tested against DuckDB 2.0.1; the allowed dependency range is `>=2.0.1,<2.1`.

## Persistent Database Consideration

A schema-qualified macro cannot currently be both temporary and stored in an
ordinary `quackframe` schema. In a persistent DuckDB file, public macros may
therefore persist while their Python UDFs remain connection-scoped.

Quackframe recreates enabled macros and private UDFs during every connection
setup. Definitions and signatures are validated before catalog changes begin,
and macro installation is transactional. Manual installation requires a connection
without an active transaction. If starting the installation transaction fails,
Quackframe raises `FunctionDefinitionError` without rolling back the caller's
transaction. DuckDB marks an existing transaction as aborted after a nested
`BEGIN`; the caller must roll it back before using the connection again.
Persisted macros remain implementation metadata in persistent databases and are
replaced on the next enabled run.

## Related Docs

- [Developer API](developer-api.md): the SQL-facing call convention.
- [Execution Lifecycle](execution-lifecycle.md): when functions are installed.
- [Credential Providers](credential-providers.md): shared model and loading contracts.
- [Filesystems](filesystems.md): standard filesystem registration and ownership.
- [Configuration](configuration.md): function enablement and optional settings.

## Running A Prefect Deployment

Install `quackframe[prefect]` and explicitly enable the function:

```toml
[tool.quackframe.functions]
enabled = ["prefect_run_deployment"]
```

Call it as a standalone statement before dependent SQL:

```sql
SELECT quackframe.prefect_run_deployment(
    deployment_id := '00000000-0000-0000-0000-000000000001'
);
```

Alternatively, select the deployment by its Prefect flow/deployment name:

```sql
SELECT quackframe.prefect_run_deployment(
    deployment_entrypoint := 'members-refresh/prod'
);
```

Use named SQL options with `:=`. Supply exactly one of `deployment_id` (a UUID)
or `deployment_entrypoint` (a flow name and deployment name separated by one
slash). Both name components must be nonblank. Names resolve on the configured Prefect server; the entrypoint is not
a Python module path or just a deployment name.

Successful completion returns the run UUID as VARCHAR. Failed, crashed,
cancelled or unfinished runs raise an error and stop subsequent SQL. Missing,
NULL or conflicting required options fail before a deployment is launched.
The unused selector may be omitted or NULL. The existing DuckDB macro machinery
also accepts positional arguments; named options keep the choice explicit.

Native `PREFECT_API_URL` and Prefect authentication settings select the server;
a missing URL is rejected rather than starting an ephemeral server. The function
works with direct or Prefect runtime, independently of the secret provider. An
existing worker or runner must be available to execute the deployment.

There is no completion timeout option. The function passes `timeout=None` to
Prefect and waits while the run is queued or running, until it reaches a final
state. Native API request timeouts still apply; a request failure stops the SQL
sequence because the outcome cannot be established. It does not cancel the remote
run. Check its state before rerunning the SQL. Each invocation passes a fresh
idempotency key to protect its create request against transport retries; separate
SQL invocations intentionally create separate runs.

Installed Python callbacks retain a copy of the context from function installation,
including settings and parent run identity, even on DuckDB worker threads. Each
call receives its own copy. Under the Prefect runtime this is the parent flow
context, because installation happens before SQL-file tasks start. Child deployment
linkage and safe diagnostics therefore refer to that flow, not necessarily the
individual SQL-file task. The function uses Prefect's native subflow linkage and
emits safe deployment/run UUID and failure state through that captured run logger. Raw API errors and state messages are omitted. Deployments must
signal business failures as failed states; a Completed state is treated as success.

## SQL Server Agent Jobs

Enable `mssql_run_job` in `[tool.quackframe.functions].enabled`, alongside
`register_secret` when SQL also registers credentials. Register the MSSQL secret
and attach its database using the existing credential-provider workflow. Then:

```sql
SELECT quackframe.mssql_run_job(
    database := 'integration_server',
    job_name := 'Refresh reports',
    timeout_seconds := 3600,
    poll_interval_seconds := 5
);
```

Alternatively supply `job_id := '12345678-1234-1234-1234-123456789abc'` instead of
`job_name`. Exactly one selector is required. Use one standalone call per intended
run; selecting this side-effecting function over rows intentionally starts a job
per invocation. EXPLAIN without ANALYZE does not start the job.

The function waits and returns a JSON report containing the job identity, Agent
session, history IDs, each recorded step attempt, status, duration, SQL error
number/severity and message. Human-readable lines also report successful and
failed steps. Detailed logs follow `allow_external_error_logging`; logging the
returned JSON through SQL result logging separately follows
`allow_external_result_logging`. SQL Agent messages can contain application data.

To retain a successful report without rerunning the job:

```sql
CREATE TABLE job_report AS
SELECT quackframe.mssql_run_job(
    database := 'integration_server',
    job_name := 'Refresh reports'
) AS report;

SELECT report::JSON FROM job_report;
```

Failure, cancellation, failed final step attempts, and unknown outcomes raise and
stop later statements/files. Failure reports remain in diagnostic logs; the
failed statement does not return a success value or persist its result table.
Native Agent retries are reported; Quackframe does not retry or resubmit.

There is no completion deadline when `timeout_seconds` is omitted or NULL.
An explicit timeout is checked between polls; `poll_interval_seconds` defaults
to 5 seconds when omitted or NULL. Supplied values must be finite and positive. Native
connection/query timeouts still govern individual remote calls. Timeout or
interruption does not stop the remote job: check SQL Agent before rerunning.

The login must be able to start the selected job and read its `msdb` job, step,
activity, session and history records. SQL Agent must retain step history during
observation. Steps with no records are listed as `not_recorded` (skipped or history
unavailable), not silently marked successful. Reports reflect SQL Agent evidence;
they cannot recover truncated messages or detect business errors swallowed by a
job step. Avoid simultaneous external starts or history purges during observation.

This function uses DuckDB 2.0 and MSSQL extension 0.3.0 or newer. Its remote
queries and job submission bind values through `mssql_scan_params` and
`mssql_exec_params`; the existing attachment owns authentication. See the
[implementation phase](epics/06-sql-orchestration/02-mssql-run-job.md).
