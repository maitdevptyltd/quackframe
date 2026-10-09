# Parameterized SQL Files And SQL-Driven Execution

Status: **Planned**
Last updated: 2026-10-09
Epic: 07 Parameterized SQL
Phase: 01
Related docs: [Developer API](../../developer-api.md), [SQL Function Extensions](../../python-extensions.md), [Execution Lifecycle](../../execution-lifecycle.md), [Runtime Adapters](../../runtime-adapters.md)

## Purpose and status

Allow reusable SQL files to receive invocation-specific values through Python
and through SQL itself. A caller should not need to generate a new SQL file for
each source path, destination path, or filter value.

This is a scope draft, not implemented functionality. The agreed direction is
one parameter-binding implementation shared by both entry points. Detailed
contracts below are proposals for review; execution feasibility remains subject
to the validation gates below.

A motivating use case is converting independently discovered files using one
conversion SQL file. File discovery, selection, skip-existing policy and output
validation belong to the consuming project, not Quackframe core.

## Feature 1: parameters per Python file invocation

Proposed public signature:

```python
class SqlFileInvocation(TypedDict):
    path: str | Path
    parameters: NotRequired[Mapping[str, SqlParameterValue]]


def run(
    sql_files: Iterable[str | Path | SqlFileInvocation],
    *,
    config: QuackframeConfig | None = None,
) -> ExecutionResult:
    ...
```

Start with a defined scalar value contract: string, boolean, integer, float and
None. Decide supported numeric limits and non-finite values during implementation.
Dates, decimals, bytes, lists and nested objects are deferred rather than silently
stringified. The exact exported type names remain a design detail.

```python
run([
    "sql/register_storage.sql",
    {
        "path": "sql/convert.sql",
        "parameters": {
            "source": "storage://input/first.parquet",
            "destination": "storage://output/first.json",
        },
    },
    {
        "path": "sql/convert.sql",
        "parameters": {
            "source": "storage://input/second.parquet",
            "destination": "storage://output/second.json",
        },
    },
])
```

Paths and dictionaries are both intentional forms of the current API, not legacy
aliases. A path means a file with no parameters. Normalize both forms once.
Preserve explicit input order and the existing shared-session execution contract.
Identical paths with different parameters are distinct invocations: no deduplication,
cross-invocation parameter inheritance or new result caching.

Parameters use names without a dollar prefix in Python and named placeholders in
SQL. Values are bound through DuckDB, never substituted with string formatting.
Parameters represent values, not SQL identifiers, keywords, or arbitrary SQL text.

Illustrative SQL, pending the COPY binding gate:

```sql
COPY (
    SELECT * FROM read_parquet($source, hive_partitioning = false)
)
TO $destination (FORMAT JSON, ARRAY true);
```

For multi-statement files, inspect DuckDB's parsed parameter metadata and bind
only the names used by each statement. The file may reuse a name in several
statements. Missing names fail before that file executes. Reject supplied names
unused anywhere in the file to catch mistakes. An explicit None is not missing.
Do not implement placeholder detection using regular expressions.

Runtime adapters carry invocation objects through to the same core executor;
they must not discard values by coercing every input to a path string. Update
the optional public Prefect flow input contract and serialization as part of
this feature. No new CLI parameter syntax is required in this scope.

## Feature 2: invoke a parameterized file from SQL

Proposed enabled extension:

```sql
SELECT quackframe.run_sql(
    'sql/convert.sql',
    MAP {
        'source': file,
        'destination': regexp_replace(file, '[.]parquet$', '.json')
    }
)
FROM glob('storage://input/*.parquet');
```

SQL supplies the rows; the extension executes the referenced file for each
evaluated call. No separate FOR language or customer Python wrapper is required.
A caller can filter discovery results before invoking the function.

Start the SQL interface with MAP(VARCHAR, VARCHAR), matching the existing
extension registrar's supported mapping type. Bind supplied values as strings;
a consuming SQL file may explicitly cast them. Typed and nullable SQL map values
are an open extension question, not an implicit equivalent of Python's full
scalar contract. Return BOOLEAN true only after the file completes; propagate
failure instead of returning false and hiding it.

Enable run_sql through the existing function allowlist. Share preparation,
parameter validation, statement execution and sanitized diagnostics with Python
invocations. Keep function-specific lifecycle decisions in its own package;
do not add a run_sql-specific queue or branch to the core runner.

Nested paths resolve from the configured runtime root, consistently with Python
calls, not from whichever process directory happens to be active. Propagate
execution context explicitly without reloading configuration or credentials.
Use the existing trusted-file policy; parameters do not grant permission to
load SQL from remote URLs.

The first scope excludes recursive SQL-file invocation. Define and test a
clear rejection of direct and indirect recursion.

## Connection and execution gates

The existing register_secret function executes mutations on a duplicate
connection because its parent connection is busy executing the UDF. This is
precedent, not proof that arbitrary nested SQL is safe.

Before implementing the SQL entry point, establish:

1. A side-effecting UDF can execute a parameterized child file without deadlock,
   reentrant use of the busy connection, or leaking connection handles.
2. The chosen connection can use configured filesystem registrations and temporary
   secrets. Verify these independently; a shared database does not imply identical
   connection-local state.
3. Precisely which settings, transactions, temporary tables and session variables
   are visible to the child. Do not promise parent-session equivalence. For the
   initial feature, child scripts should be self-contained apart from explicitly
   supported registered resources.
4. Every child statement executes before the function returns, resources close on
   success and failure, and a child error fails the enclosing file.
5. Calls driven by SELECT are marked as side-effecting. Document that row order is
   not guaranteed and filtered or limited queries may execute only selected calls.
   Do not promise exactly-once side effects, rollback of external writes or
   all-or-nothing completion of a row set.
6. Native bound values work in read_parquet and COPY destinations on supported
   DuckDB versions. If COPY TO $destination is unsupported, evaluate a safely bound
   session-variable/expression convention and document its connection scope.
   Do not fall back to interpolating values into executable SQL.

If duplicate connections cannot meet the resource and execution contract, stop
and revise the SQL feature design. The Python parameter feature can ship
independently; do not conceal an incompatible session model behind one API.

## Observability and data handling

Preserve ordered, fail-fast Python execution and core independence from Prefect.
SQL child calls are not automatically individual Prefect tasks. Initially retain
the parent task and record safe child execution context: file identity, invocation
ordinal, statement number, duration and success/failure. Final child-result shape
and public result accounting require review.

Quackframe-generated logs, exception text, result objects and preparation caches
must not retain parameter values or rendered SQL containing them. Audit Prefect
task/flow input persistence as well as console logging: accepting a dictionary
must not silently publish its contents to the orchestration server. Use provider
references rather than credentials as workflow parameters.

Run nested files through the same result-logging policy and external logging
permission checks as top-level files. Do not create a second result-output path
that bypasses those checks. Deliberately logged SQL results may include supplied
values; existing explicit result-logging permission still applies.

## Delivery sequence and acceptance criteria

1. Verify native named binding, COPY behavior and per-statement parameter metadata.
2. Implement the common invocation and binding model plus Python/runtime propagation.
3. Verify the duplicate-connection gates before implementing the SQL extension.
4. Update developer API, extension, lifecycle and optional Prefect documentation;
   add small neutral examples using the verified SQL syntax.

Future implementation acceptance checks (not run for this draft):

- Mixed path/dictionary inputs and repeated files receive the correct isolated values.
- Multi-statement files bind their own parameter subsets; missing/extra names and
  unsupported types fail predictably without exposing values.
- Quotes, newlines and SQL-looking strings remain data; literals and comments
  containing dollar signs are not interpreted as placeholders.
- Python invocations retain shared-session ordering, cleanup and fail-fast behavior.
- The same parameterized conversion works through direct and optional Prefect
  runtimes with synthetic local files.
- SQL-driven discovery converts every selected synthetic file, handles zero rows,
  propagates a child failure and closes owned resources without hanging.
- Parent/child visibility, recursion rejection and COPY binding match the documented
  contract on every supported DuckDB version.
- Parameter values do not leak through framework diagnostics or orchestration input
  persistence; nested result logging obeys the parent's permission policy.
- Existing parameterless file runs and SQL extensions still behave as documented.

No live storage tests, credentials or production migrations are part of this
scope draft. No implementation or tests have been executed for this document.

## Non-goals and open decisions

Non-goals: a general procedural SQL language, automatic parallel migration,
automatic retries, atomic remote file writes, SQL templating, dynamic identifiers,
customer-specific conversion logic, or a new orchestrator.

Open decisions: exact public scalar types and exports; SQL parameter map typing;
verified COPY destination syntax; child connection visibility; recursion detection;
safe Prefect parameter transport; nested result accounting and logging policy.
Resolve these through focused synthetic validation before finalizing the contract.

## Related Docs

- [Developer API](../../developer-api.md): current path-only Python entry point.
- [SQL Function Extensions](../../python-extensions.md): registry, side effects and
  duplicate-connection precedent.
- [Execution Lifecycle](../../execution-lifecycle.md): session and failure invariants.
- [Runtime Adapters](../../runtime-adapters.md): runtime parity and optional Prefect.

