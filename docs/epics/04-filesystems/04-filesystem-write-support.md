# Filesystem Write Support

Status: **In Progress**
Last updated: 2026-10-07
Epic: 04 Filesystems
Phase: 04
Related docs: [Filesystems](../../filesystems.md), [Azure Strategies](03-azure-filesystem-strategies.md), [Named Protocols](02-aliased-filesystem-registrations.md), [Execution Lifecycle](../../execution-lifecycle.md)

## Purpose And Review Status

Every strategy exposed by `quackframe.register_filesystem` must support writing
data as well as reading it, subject to the permissions of the selected credentials
and destination. SQL remains the authoring surface: callers register a filesystem
and use DuckDB `COPY ... TO` with its named protocol.

The user explicitly requested this requirement and a draft scope on 2026-10-01.
Implementation was authorised on 2026-10-01 after confirming that the strategy
pattern, registration signature and changes confined to the filesystem package
would be preserved. The requirement covers all three existing strategies and establishes a
write-support acceptance requirement for future strategies.

The user confirmed the access-control intention on 2026-10-01: Quackframe must
enable both read and write operations for every filesystem strategy. The person
configuring the credentials and remote permissions controls the access level.
Quackframe must respect that access level without imposing an additional
read-only restriction or requiring a separate write-enable setting.

For Azure, the selected credentials or identity and the storage service's
authorization rules determine permitted operations. For SFTP, the SSH key
authenticates a server account; that account's filesystem permissions and server
restrictions determine permitted operations. Access can differ by destination
within the same registration. Credential possession alone does not grant write
access, and registration must not bypass or broaden remote permissions.

The earlier Azure phase excluded writes without recording a rationale or explicit
approval of that exclusion. This phase restores writes to the intended scope.
The earlier phase remains evidence of what was delivered, not authority to omit
writes from this work. Any proposed reduction of the requirement must be recorded
here with its reason and reviewed with the user before implementation proceeds.

## Current Gap

| Strategy | Current implementation | Required outcome |
| --- | --- | --- |
| `sftp` | The adapter forwards file modes, but integration coverage uses a read-only server. | Verified remote writes and read-back through real DuckDB and SFTP. |
| `azure_connection_string` | The Azure backend explicitly rejects every mode except `rb`. | Blob and ADLS Gen2 writes with the selected account key or SAS credentials. |
| `azure_managed_identity` | Uses the same read-only Azure backend. | Blob and ADLS Gen2 writes with the selected system-assigned or user-assigned identity. |

Registration itself does not prove permission to write. Read-only credentials
remain valid for reading; attempted writes must fail safely when access is denied.
Registration must not create a probe file or require write permission up front.

On 2026-10-01 the user also authorised container-first Azure URLs for both
strategies: `protocol://container/blob-name`. The storage account is taken from
the existing credentials/configuration and never repeated in filesystem URLs.
The container remains explicit. The [Azure phase](03-azure-filesystem-strategies.md)
owns this path change; the write contract and strategy pattern remain unchanged.

## Public Contract

Keep the existing signature, credential models, provider selection, named protocol
rules and optional dependency bundles. Do not add a separate write registration
function or a new write-enable flag. A registration exposes the capabilities of
its strategy using its explicitly selected credentials.

These examples use the implemented registration and export path:

```sql
SELECT quackframe.register_filesystem('prefect', 'output-files', 'sftp');
COPY (SELECT 42 AS value)
TO 'output-files://files.example.test/exports/result.parquet'
(FORMAT PARQUET);
```

```sql
SELECT quackframe.register_filesystem(
    'prefect', 'output-blobs', 'azure_connection_string'
);
COPY (SELECT 42 AS value)
TO 'output-blobs://reports/result.csv'
(FORMAT CSV, HEADER);
```

The managed-identity strategy must support the same export operations. Prefect
in these examples is an optional credential provider; direct execution and other
providers must work without a Prefect dependency.

### Output Operations

- Create CSV and Parquet files from DuckDB queries and read the resulting data
  back through the same registration.
- Support replacing an existing single output file according to the selected
  DuckDB version's `COPY` semantics. Verify and document those semantics rather
  than adding a Quackframe-specific overwrite default.
- Support partitioned and multi-file CSV/Parquet exports, including the directory
  operations that DuckDB needs for the selected output options. Verify explicit
  append and overwrite options separately; never silently ignore an option.
- Support nested output paths. Create filesystem directories when the requested
  DuckDB operation requires them. Existing Azure containers and storage accounts
  are prerequisites; registration must not provision infrastructure.
- Preserve existing endpoint validation, account isolation, explicit full paths,
  percent encoding and named-protocol selection for writes and discovery alike.
  Scope must not become an implicit output root or a new access-control boundary.

Dataset append means adding output files through supported DuckDB options. It does
not promise arbitrary byte append or random modification of an existing file.
Removal or replacement needed for an explicit export option is in scope; a general
filesystem administration API is not required.

### Completion And Failure

A successful SQL export means all required file writes, flushes and finalization
have completed successfully. Deferred upload or close failures must fail the
statement; session cleanup must not turn an incomplete export into success.
Subsequent SQL files in the same session must be able to read completed output.

Preserve ordered execution, failure attribution, fail-fast behaviour and cleanup
under direct execution and optional runtime adapters. Do not introduce automatic
retries or transactional guarantees for remote files. A failed export may leave
partial output; document observed backend behaviour and caller recovery choices.
Do not delete pre-existing output as an automatic failure-recovery action.

Credentials, SAS tokens, connection strings and returned query data must remain
absent from generated SQL, logs and errors, including deferred write, flush,
commit and close errors. Preserve useful operation context without exposing
backend exception payloads. Bind values in any generated SQL.

## Implementation Direction

Keep the change local to the existing filesystem extension and its tests.
Inspect DuckDB's actual filesystem calls for single-file and partitioned output
before deciding which adapter methods to implement. Forward required operations
through the existing path validation and backend ownership boundaries; inherited
fsspec defaults must not silently skip required work.

Replace the Azure read-only restriction with the file modes required by the
accepted output operations. Extend error handling to the entire returned file
lifetime, including upload finalization. Retain explicit client selection,
credential isolation and deterministic closure of the client and owned identity.

For SFTP, verify file writes and finalization under the existing serialized
transport contract. Preserve read concurrency regressions. If a write path
bypasses exchange serialization, address it and prove mixed read/write behaviour
before claiming support. Do not assume that removing a mode restriction or
passing a mocked `open()` call establishes end-to-end capability.

Keep runner, registrar and credential-provider contracts neutral. No new
orchestrator dependency, credential store, background upload service or generic
copy framework is needed. Future filesystem strategies must meet the same write
acceptance criteria or receive an explicitly reviewed contract change.

## Validation And Acceptance

Exercise every strategy through SQL registration and real DuckDB `COPY ... TO`.
Use temporary destinations with deterministic cleanup and compare read-back data,
not just file existence or successful backend calls.

- [x] Each strategy exports CSV and Parquet, including empty and multi-batch data,
      and reads the complete results back.
- [x] Existing-file replacement, partitioned output, nested paths, dataset append
      and explicit overwrite options have documented, verified behaviour.
- [x] Two registrations in one session write to their selected destinations
      without crossing credentials, endpoints or accounts.
- [x] Encoded filenames and invalid/mismatched URLs retain the read-path rules.
- [x] Read-only credentials still read successfully; denied writes fail safely.
- [ ] For every strategy, remote permissions control access: credentials with
      write permission can write without another Quackframe setting, and
      credentials without that permission cannot write. Denied reads also fail
      safely; registration does not grant access or require both permissions.
- [ ] Open, write, flush, finalization and close failures produce failed execution,
      skip later SQL files, preserve the primary failure and release resources.
- [x] Sensitive canary values never escape through errors, logs or observations.
- [x] SFTP uses a writable loopback server and tests parallel output plus mixed
      reads/writes; existing concurrency and host-key checks continue to pass.
- [x] Both Azure strategies use real DuckDB and adlfs with controlled service
      responses that exercise upload, finalization and failure paths.
- [ ] Live Azure evidence covers Blob and ADLS Gen2, account-key and SAS access,
      and system-assigned and user-assigned identity. Record unavailable cases
      explicitly; mocked identity tests do not establish deployed identity access.
- [x] Ordered multi-file direct execution proves export followed by read-back;
      optional Prefect execution preserves completion, failure and cleanup.
- [x] Developer docs and runnable examples describe reads and writes, permissions,
      overwrite/append behaviour, partial output and validation limitations.
- [x] No registered strategy remains intentionally read-only.

Keep automated local results separate from live-service evidence. If an
environment or dependency prevents an acceptance case, record the limitation
and resolve it with the user rather than silently removing that case or marking
the full contract complete.

Run focused filesystem tests first, then the repository checks:

```powershell
poetry run pytest
poetry run ruff check .
poetry run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

## Delivery Sequence

1. Review this draft's output semantics and acceptance boundaries.
2. Set this phase to `In Progress`; probe the installed DuckDB/fsspec/backend
   versions and record the operations required for every export shape.
3. Implement adapter and backend support with regression coverage for all
   strategies, preserving existing reads and ownership semantics.
4. Verify live integrations, update developer documentation and examples, and
   report any remaining evidence gaps before marking the phase complete.

No new storage backend, ACL administration, remote transaction manager or
cross-filesystem atomic commit is proposed. These boundaries do not exclude
operations needed to deliver the export behaviours listed above.

## Implementation Evidence (2026-10-01)

Azure filename compatibility follow-up: preserve literal `=` in discovered paths
and reader filenames for partition extraction. Continue escaping percent signs,
URL delimiters and literal glob characters, with one decode on read. Implemented
regression coverage exercises partitioned BLOB/CSV exports, discovery,
filename-based account/date extraction and special-character round-tripping for
both Azure credential strategies. The focused Azure/write suite passes **135
tests**; Pyright, source/test/example Ruff, Markdown links and whitespace checks
pass. The phase remains **In Progress** pending the existing live-service
evidence below; this follow-up uses controlled Azure SDK responses.

The follow-up full suite reports **395 passed, 4 failed, 1 teardown error**.
The failures are the previously recorded four-thread raw Paramiko/fsspec
diagnostic timeouts. The mismatched-fingerprint SFTP test had a connection-reset
error during server teardown and passed independently on rerun. Repository-wide
Ruff still reports existing prototype issues under `MAD.Utilities.DuckDB`.

Production changes remain inside `sql_functions/register_filesystem`. The public
function, strategy registry, credential models, providers, runner and runtime
adapters retain their existing contracts.

- `ProtocolFileSystem` forwards directory creation, removal and move operations
  with both move endpoints validated. DuckDB 1.5.5 expects directory-relative
  listing names during recursive overwrite; `glob()` still returns full URLs.
- `SafeFile` sanitizes deferred file-operation errors for every strategy and
  translates Paramiko's successful `write()` return of `None` into a byte count.
- The Azure backend no longer blocks write modes. It requires pre-existing
  containers and streams replacement copies through its selected SDK client,
  awaiting upload completion before removing the exact source path.
  This avoids adlfs's unawaited server-side copy and anonymous source-URL access.
  Move and removal paths never expand decoded wildcard characters; neighboring
  files remain untouched.
- SFTP file operations share the connection's exchange lock because Paramiko
  writes bypass `_request`. Explicit file close checks the server acknowledgement
  instead of inheriting Paramiko's suppression of close errors.
- Real DuckDB SQL tests cover all three strategies with CSV/Parquet, empty and
  non-empty exports, nested partition paths, append and explicit overwrite.
  Replacements change the data to prove fresh output rather than file existence.
  Azure tests retain real adlfs buffering and use small test blocks to exercise
  multi-block upload, with controlled SDK responses in place of network access.
- Failure tests cover denied SFTP writes with successful reads, Azure staging and
  finalization errors stopping later SQL files, safe deferred errors and the
  prohibition on implicit container creation. Mixed concurrent SFTP file reads
  and writes exercise the shared transport lock.

Single-file SFTP output requires an existing parent directory; partitioned output
creates the directories DuckDB requests. Single-file replacement uses DuckDB's
temporary-file/move behaviour and the SFTP server's POSIX rename extension.
Azure replacement streams through the client and can require read/delete access
as well as write access. Remote writes are not transactional. Empty partitioned
exports create no data files.

Validation results:

- Final regression pass: **363 passed, 4 deselected**. The four exclusions are the
  existing `test_layer_diagnostics` raw Paramiko/fsspec cases with four threads,
  traced and untraced. The preceding unrestricted run completed with **347 passed
  and those four timeouts**; they bypass Quackframe's serialized client.
- The expanded write module passes **43 tests**, including direct and Prefect
  export/read-back and failed-upload cleanup. The additional two-endpoint SFTP
  write-isolation regression passes independently after its fixture query fix.
- `poetry run pyright`: **0 errors, 0 warnings**.
- `poetry run ruff check src tests examples`: passes. Repository-wide
  `poetry run ruff check .` reports pre-existing issues under the untouched
  `MAD.Utilities.DuckDB` prototype; no prototype cleanup is included.
- Local Markdown links, terminology review and `git diff --check`: pass.

The phase remains **In Progress** pending live Azure Blob/ADLS Gen2 and deployed
identity evidence and completion of the remaining acceptance evidence. No live credentials or deployment were supplied for this
implementation; controlled SDK tests do not prove live service authorization.
This is an outstanding validation requirement, not a removal of write scope.

## Related Docs

- [Filesystems](../../filesystems.md): current public registration behaviour.
- [Azure Strategies](03-azure-filesystem-strategies.md): previous read-only scope
  and Azure authentication/client ownership.
- [Named Protocols](02-aliased-filesystem-registrations.md): isolation and path rules.
- [Credential Providers](../../credential-providers.md): shared credential contracts.
- [Execution Lifecycle](../../execution-lifecycle.md): ordering, errors and cleanup.

## SFTP Reconnection Ownership Correction (2026-10-07)

Distinct-client regressions confirmed that reconnecting leaked the previous SSH
client and SFTP channel, while failed replacements left a mismatched owned pair.
The adapter now builds a complete replacement before assigning ownership and
attempts closure of both superseded resources. Failed setup closes only the new
client and preserves the prior pair. Focused tests cover successful replacement,
connect/transport/channel failures and old-channel cleanup failure. The phase
remains **In Progress** for its existing live-service validation requirements.
