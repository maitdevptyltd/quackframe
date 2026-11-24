# Run SQL Server Agent Jobs

Status: **Complete**
Last updated: 2026-11-23
Epic: 06 SQL Orchestration
Phase: 02
Related docs: [SQL Functions](../../python-extensions.md)

## Contract

An explicitly enabled `quackframe.mssql_run_job` calls an existing SQL Agent job
through an existing authenticated MSSQL attachment. Exactly one job ID or name
selects the job. Start once, poll completion, report every available step attempt,
and fail the SQL statement on failure, cancellation, or unknown outcome. No
framework retries or automatic cancellation of the remote job.

## Implementation

The self-contained function package owns the SQL Agent client, records, polling
and reporting. A duplicate DuckDB connection avoids reusing the connection busy
executing the Python UDF. The generic resource owner carries the runtime logger
and diagnostic policy; core execution has no SQL Agent-specific branches.

Use DuckDB 2.0 with MSSQL extension 0.3.0 or newer. The transport binds the
attachment name, fixed T-SQL and parameter STRUCT through `mssql_scan_params`
for reads and volatile `mssql_exec_params` for the single start. All result sets
are consumed before the next operation, including attachment validation.

Capture Agent session and history watermark, reject already queued/running jobs
and a changed watermark immediately before submission, and stop at the first
terminal step-zero history record. Do not absorb a later execution's history.
Agent restarts and monitoring failures cannot be interpreted as success.
A successful job summary cannot conceal a failed final step attempt, and a
summary without any step evidence for a configured job is unknown. Absent
individual steps are reported as not recorded: they may be skipped branches or
unavailable history. The runner does not infer business errors swallowed by jobs.

## Polling and timeout agreement — 2026-11-23

`poll_interval_seconds` is optional and defaults to 5 seconds. Omitting
`timeout_seconds` (or supplying NULL) means no completion deadline. An explicit
timeout must be finite and positive and fails observation without stopping the
remote job. Individual connection/query timeouts remain separate.

The SQL implementation lives on `feat/mssql-job-execution`. The separate
`feat/prefect-execution-controls` branch is reserved from `feat/setup` for a
follow-up: expose the same two optional arguments on `prefect_run_deployment`,
with the same five-second polling default and no default completion deadline.
Pass them to Prefect's SDK and fail if an explicit deadline returns a non-final
run; do not cancel the remote flow. Preserve parent-child linkage, execution once,
and failure propagation. This Prefect change is planned, not implemented here.

## Validation

Offline tests cover validation, named SQL registration, no launch during EXPLAIN,
one submission, a real DuckDB duplicate/UDF boundary, waiting through in-progress
history, terminal correlation, native retries, step failures hidden by job success,
timeout, lost responses, external diagnostic policy, and ordered-file fail-fast.
No customer system access or live SQL Agent execution is authorized by these tests.
A separately authorized dummy-job acceptance test remains the deployment check.

Implementation verification on DuckDB 2.0.1: 191 focused feature, registry,
resource, execution, diagnostic and Prefect orchestration tests passed. Independent
review also exercised the real MSSQL 0.3.0 parameterized function inside a duplicate
connection/UDF using a nonexistent attachment; it failed at attachment lookup as
expected and left the root connection usable. This does not establish live SQL
Server permissions or job execution. Ruff, formatting, Pyright, documentation
links and whitespace checks passed. No release-history suite was run.

The parameterized transport replaces the former DuckDB 1.5 literal renderer;
there is no fallback or legacy API retained.

## Related Docs

- [SQL-owned orchestration](01-sql-owned-integration-orchestration.md): ordered SQL work.
- [Execution lifecycle](../../execution-lifecycle.md): failure attribution and cleanup.
