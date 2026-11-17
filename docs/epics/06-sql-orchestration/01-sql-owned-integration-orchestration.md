# SQL-Owned Integration Orchestration

Status: **Complete**
Last updated: 2026-11-17
Epic: 06 SQL Orchestration
Phase: 01
Related docs: [Roadmap](../../roadmap.md)

## Outcome And Scope

Let SQL developers own an integration's sequence while calling existing Prefect
deployments when Python work is needed. A Windows scheduled task can launch
Quackframe, which runs SQL in order and records execution in Prefect. The SQL
author can refresh source data, reconcile records, build outbound requests, and
then invoke the deployment that sends them. Each step must finish successfully
before the next starts.

The initial SQL function, Prefect flow-name override and automatic interface tag
are implemented and reviewed for the initial delivery. Source history, custom tag
arguments and failure-reporting work remain future scope. Quackframe remains independent of
Prefect in its core; Prefect capabilities belong to optional integrations.

The intended ownership is straightforward:

| Responsibility | Owner |
| --- | --- |
| Schedule and launch the command | Windows Task Scheduler or another external scheduler |
| Define order, reconciliation and request-building logic | SQL author in a consuming repository |
| Execute ordered SQL and stop on failure | Quackframe |
| Execute an existing deployment and expose its state | Prefect |
| Deliver a useful failure email | Later reporting integration |

This does not require deploying the entire SQL workflow as a Prefect deployment.
It also does not introduce a DAG engine, recursive SQL-file execution, or a new
scheduler inside Quackframe.

## Existing Foundation

The CLI already accepts multiple SQL files in explicit order. They execute in
one shared DuckDB session and stop at the first failure. With the Prefect runtime,
one invocation produces a flow run and each SQL file is represented by a task.
The current adapter uses the flow name `quackframe-run`, the configured project
name for the flow run name, and each SQL file's stem for its task name.

The existing command shape is:

```shell
quackframe run --runtime prefect 01_refresh.sql 02_reconcile.sql 03_build_requests.sql 04_send.sql
```

Both the ordered-file command and deployment calls inside its first and last
files are now implemented. Calling the files in one invocation preserves shared session state.
Running four separate commands would create separate sessions and runs.

## SQL API

Preserve the public `quackframe` namespace and identify Prefect explicitly:

```sql
-- Run once as a standalone statement, then wait for success.
SELECT quackframe.prefect_run_deployment(
    deployment_id := '00000000-0000-0000-0000-000000000001'
);
```

Alternatively, select by Prefect's flow/deployment name:

```sql
SELECT quackframe.prefect_run_deployment(
    deployment_entrypoint := 'members-refresh/prod'
);
```

The UUID and names are illustrative. Named SQL options use `:=`. Supply exactly
one selector: `deployment_id` must be a UUID; `deployment_entrypoint` must contain
exactly one slash with a nonblank flow name and deployment name. The entrypoint
is the native Prefect flow/deployment name, not a Python module entry point.
The unused selector can be omitted or NULL; supplying both or neither fails
before launch. There is no completion timeout option.

The existing macro framework uses None defaults to expose named options and
also accepts positional arguments; this change does not add keyword-only
execution machinery. The function returns the successful run UUID as VARCHAR.
The native Prefect call uses `timeout=None` and waits through queued and running
states until a final outcome. Individual API requests still use native Prefect
connection timing settings.
Credentials and server configuration stay outside SQL through the existing
native integration configuration boundary.

The function belongs in the explicit SQL-function registry and must be enabled
through the consuming project's function allowlist. Installing a Prefect extra
must not enable it automatically. Mark it as having side effects; do not cache
calls or allow constant folding to launch work unexpectedly. The supported usage
is one standalone call per intended deployment run, not a SELECT over table rows.

### Completion And Failure Contract

- Validate exactly one deployment selector before launch.
- Start one deployment run and wait for its final outcome. Submission alone is
  not success, and a polling return value alone is not proof of completion.
- Return successfully only when the deployment run completes successfully.
  The result is its flow run ID as VARCHAR.
- Failed, crashed or cancelled runs must raise a SQL-visible error. A launch
  failure or inability to establish the outcome must also fail the call.
- Queued and running states keep waiting without a completion deadline. An
  unexpected return without a final state is a defensive error, not a timeout.
- Preserve safe context: deployment ID, child run ID when known, final state,
  and an actionable error. Do not expose credentials or arbitrary result data.
- Installed callbacks copy their installation context for each invocation so
  DuckDB worker threads retain settings and parent flow identity. Installation
  precedes SQL-file tasks, so child linkage and safe logs attach to the parent
  flow rather than guaranteeing attachment to the current SQL-file task.
- The error must fail the current SQL script, stop later statements and files,
  fail the parent Prefect run when using that runtime, and produce a nonzero
  CLI exit status. Do not catch the error and continue to the outbound step.
- An API failure does not prove that the remote run was cancelled. Report that
  uncertainty. The function does not request cancellation.
- Do not automatically launch a replacement after an ambiguous network failure.
  Retry and idempotency behaviour need an explicit design so a retry cannot
  silently duplicate a remote write.

A deployment that swallows business errors and finishes as Completed cannot be
identified as failed from its state alone. Consuming deployments must propagate
unsuccessful API operations into a failed run, or define a separate explicit
result contract. This is a prerequisite for reliable end-to-end alerts.

## Authoring The Sequence

Both layouts should work without a function for loading other SQL files:

1. One SQL file contains the deployment call, reconciliation SQL, request-building
   SQL and final deployment call, in that order.
2. Several SQL files contain those steps and are supplied to one CLI invocation
   in the required order.

For example, membership synchronisation would:

1. Call a Python deployment that fetches current source-system client groups and
   writes a complete, usable snapshot or delta to the data lake.
2. Use the existing application change-selection process to identify groups
   needing updates, then read their current source membership from the lake.
3. Reconcile memberships and insert consolidated outbound requests into the
   integration table using the endpoint's required HTTP method.
4. Call the integration-table deployment to send those requests.

The source refresh must succeed before reconciliation begins. Keep the existing
business trigger under the SQL author's control rather than inventing a second
independent schedule or change detector. The precise lake publication contract,
change selection and request deduplication belong to the consuming integration.

Consolidation must preserve members added directly in the source while handling
intentional removals explicitly. A blind union cannot support removals. A refresh
also does not eliminate changes between reading and writing; conditional writes
or another concurrency strategy require investigation in that integration.
Quackframe provides sequencing, not a guarantee that membership logic is correct.

## Prefect Flow Names And Tags

Many scheduled integrations can share one Prefect server. Give each integration
a stable flow identity rather than requiring every job to appear under
`quackframe-run`.

CLI:

```shell
quackframe run --runtime prefect --flow-name example-members 01_refresh.sql 02_reconcile.sql 03_build_requests.sql 04_send.sql
```

`--flow-name` changes the Prefect flow name, which groups runs for the integration.
It is distinct from the flow run name, which labels an individual execution.
Keep `quackframe-run` as the default when no override is supplied, and preserve
the current project-derived flow run naming unless separately configured.

Accept `--flow-name` only when the effective runtime is Prefect, including when
that runtime comes from configuration. Reject it clearly for other runtimes;
do not silently ignore it. The CLI help must explain this restriction. Config
and Python API parity should follow the existing typed configuration design;
`flow_name`, `QUACKFRAME_FLOW_NAME` and `load_config(flow_name=...)` share the
same validation. Any separate run-name override remains future work.

Apply `interface:quackframe` automatically to the parent run. Customer,
integration and environment naming can be expressed in the flow name. There is
no custom `--tags` argument in this scope; caller-supplied tags are deferred.
Native Prefect subflow linkage connects deployments to the calling context.


## Editing SQL With Change History

SQL authors need quick edits while maintainers need to see what changed and which
version executed. Keep consuming SQL in Git and record the repository, commit
SHA and script paths with each invocation.

A proposed workflow permits direct commits and pushes to a designated integration
branch where repository policy allows it. This is a policy decision for the
repository owner, not a requirement to bypass protections or allow force pushes.
The goal is a short edit-to-run cycle with attributable history.

A launcher could obtain the selected committed revision before execution and
then run an immutable checkout of that revision. Do not change files during a
run or mix revisions across steps. Define how uncommitted interactive edits are
reported rather than incorrectly attributing them to the last commit. Checkout,
update and provenance support are follow-on work, not existing CLI behaviour.

## Later Failure Reporting

Add a centrally managed failure notification path for Prefect runs tagged
`interface:quackframe`. A Prefect automation or failure handler could call a
webhook-backed reporting service that emails the integration owner. Verify the
actual server's capabilities before choosing the mechanism; do not assume a
particular hosted email feature is available.

The report should reproduce the useful information in an existing job-failure
email:

| Field | Intended content |
| --- | --- |
| Integration | Stable flow name and individual run name |
| Failed step | Step number, SQL filename and task name |
| Target | Safe logical database or service name where available |
| Operation | Script or command reference, without sensitive SQL values |
| When | Execution time with explicit timezone |
| Outcome | Final failure state and safe actionable error |
| Investigation | Parent run link, child run link where relevant, and source revision |

Each file already supplies a useful task boundary. A single-file workflow also
needs statement context or explicit step labels to identify its failed operation;
file-level task names alone cannot provide that detail.

Notify once for the failed integration after applicable retries, avoiding duplicate
emails for child, task and parent failures. Define recipients, crash/cancellation
handling and stuck-run detection separately. Failure to launch Python or contact
Prefect may leave no Prefect run to alert on, so scheduler/launcher failure
monitoring remains necessary. Diagnostics must follow existing safe error and
logging contracts rather than copying full SQL or returned data into email.

## Delivery And Acceptance

The initial delivery covers the deployment function, error propagation,
configurable flow identity and the automatic interface tag. Source provenance,
custom tag arguments and email reporting remain separate follow-on work.

- [x] A SQL call starts the specified deployment once and waits for completion.
- [x] Synthetic success, failure, crash, cancellation and API-error cases
  prove the completion contract without contacting customer systems.
- [x] Failure in the refresh prevents reconciliation, request creation and sending.
- [x] Failure in a later deployment fails the script and parent run and exits nonzero.
- [x] Both single-file and ordered multi-file layouts retain shared-session and
  fail-fast behaviour without implicit retries or caching.
- [x] Flow-name overrides produce distinct stable Prefect flow identities;
  direct-runtime misuse is rejected and the existing default still works.
- [x] Parent runs carry `interface:quackframe`; no custom tag argument is exposed.
- [x] Base Quackframe still installs and executes without Prefect; the deployment
  function remains explicitly allowlisted and its dependency errors are clear.
- [ ] Later provenance work identifies the actual revision executed, including a
  clear policy for uncommitted edits.
- [ ] Later reporting identifies the failed step with safe context and deduplicates
  notifications; a launch failure outside Prefect has a separate reporting path.

## Open Design Decisions

- Future configurable polling intervals; completion has no imposed deadline.
- Whether deployment parameters are needed in the first version and their typed
  SQL representation; no arbitrary parameter JSON is required by this proposal.
- Optional cancellation and SQL-level retry policy; initial calls use native
  subflow linkage and a fresh idempotency key for each submission.
- Future deployment parameter support beyond deployment defaults; direct runtime
  use with the Prefect extra is supported by the initial implementation.
- Future custom tag arguments and the required reporting metadata fields.
- Consuming-repository edit policies, revision selection and launcher ownership.
- Notification transport, recipients and deployment result-signalling prerequisites.

## Related Docs

- [Runtime Adapters](../../runtime-adapters.md): optional Prefect ownership.
- [SQL Function Extensions](../../python-extensions.md): registry and SQL namespace.
- [Execution Lifecycle](../../execution-lifecycle.md): order, session and failure contracts.
- [Configuration](../../configuration.md): typed settings and overrides.
- [Useful Error Diagnostics](../02-result-logging/02-useful-error-diagnostics.md): safe actionable errors.
- [Epics](../README.md): phase tracking.

## Initial Delivery Validation

Focused deployment, CLI, configuration and runtime checks passed (174 tests).
The real Prefect API-log regression also passed in the broader run. Ruff,
Pyright, local documentation links and whitespace checks passed. The independent
reviewer verified real Prefect synchronous dispatch against a mocked client and
checked compatibility with the supported Prefect 3.2 API.

The broad suite was stopped during unrelated release checks and is not claimed
as a full pass. Three subprocess tests initially lacked relative fixture paths
because the runner used an isolated temporary working directory; all three
passed when their required test files were supplied there. Tests used synthetic
configuration and no live customer or deployment calls.
