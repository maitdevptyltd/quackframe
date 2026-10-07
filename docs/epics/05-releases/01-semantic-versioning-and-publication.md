# Semantic Versioning And Package Publication

Status: **In Progress**
Last updated: 2026-10-05
Epic: 05 Releases
Phase: 01
Related docs: [Release Guide](../../releases.md), [Roadmap](../../roadmap.md), [Developer API](../../developer-api.md), [Contributing](../../../CONTRIBUTING.md)

## Outcome

Give Quackframe a documented compatibility policy and a repeatable release
process: automatically publish release candidates from `release/next`, validate
them in a consuming project, and promote them through a pull request to `main`
for automatic stable publication. Compatible fixes can publish directly from
`main` after normal pull-request review.

The release-flow decisions below were agreed on 2026-10-02. Repository
implementation now includes regressions and fixes for the seven confirmed review
findings. Production activation and end-to-end publication remain outstanding.
The 2026-10-05 clarifications below make the existing release rules
and their acceptance evidence explicit. Operator instructions live in the
release guide.

## Accepted Decisions

- Keep Poetry for dependency and environment management and Hatchling for builds.
  This is now an explicit selection, not an inference from the initial scaffold.
- Use `main` for stable releases and `release/next` for the upcoming release.
- Automatically publish an RC to PyPI when qualifying changes merge into
  `release/next` and validation succeeds. No separate manual RC request is needed.
- Review candidate scope and consuming-project behaviour before merging a
  promotion PR from `release/next` to `main`. That merge triggers stable publication.
- Review compatible fixes through PRs directly to `main`; their merges trigger
  patch publication. Bring the fixes back into `release/next` afterward.
- Bootstrap with `0.1.0rc1`, then increment RC numbers for qualifying candidate
  updates. The first stable promotion publishes `0.1.0`, subject to verifying
  remote tags and PyPI history before enabling the workflow.

This supersedes the earlier proposal for a manually prepared version-and-changelog
PR on `main`. The promotion PR carries the accumulated candidate changes, rather
than merely release metadata. The main release-flow decisions are settled; the
remaining tooling details below must implement that flow.

## Baseline Before Implementation

- `pyproject.toml` declares `[project].version = "0.1.0"`.
- Poetry manages dependencies and development environments. Hatchling is the
  declared build backend and owns wheel and source-distribution packaging.
- GitHub CI validates changes on pull requests and pushes to `main`; there is
  no release-preparation or publication workflow.
- No release policy, changelog, or Commitizen configuration exists. No local
  Git tags were present during inspection; remote tags and PyPI history must
  be checked before deciding that this is a first release.
- Agent guidance allows removal of superseded APIs before the first release.
  It does not yet define compatibility obligations for published `0.x` packages.

## Direction And Boundaries

Python Semantic Release 10.7 is selected for Conventional Commit analysis,
branch-aware version calculation and changelog generation. It replaces the
initial Commitizen proposal because it supports the agreed multi-branch flow
without building a separate version engine. Temporary-Git-history tests must cover
bootstrap, promotion and parallel stable patches. Small repository helpers must
enforce candidate-tree identity, skip synchronization-only releases, and verify
artifacts. Existing tests exercise parts of these contracts; passing them alone
does not establish the acceptance coverage defined below.
Use GitHub Actions for validation and publication, and
PyPI Trusted Publishing for package upload. Here, semantic release describes
the strategy; it does not introduce the JavaScript `semantic-release` tool.

Keep Hatchling and the existing package layout. Add development tools through
Poetry and retain `poetry.lock`; do not introduce another environment manager.
Use a Poetry-managed build frontend that invokes the declared Hatchling backend,
and prove that path in validation rather than assuming every build command uses
the backend identically.

Use the agreed standing branches `main` and `release/next`. Feature PRs target
`release/next`; compatible stable-fix PRs target `main`. Follow the repository's
convention for short-lived branches. This scope does not create any branch.

Out of scope: runtime changes, customer deployment automation, cross-project
release tracking, automatic stakeholder messages, multiple supported maintenance
lines, and additional prerelease channels beyond the agreed RC line. Add those
only when needed.

## Compatibility Policy

The implementation must use the scope's `0.x` bump rules and prevent
an accidental initial `1.0.0`. The interview explicitly confirmed the bootstrap
sequence; it did not separately establish a long-term support commitment. A
future `1.0` readiness decision remains outside this phase.

Use `MAJOR.MINOR.PATCH` for stable package versions, expressed in PEP 440 form
for Python packaging. Git tags are `vX.Y.Z`; package metadata omits
the `v`. RC package versions use PEP 440 syntax, such as `0.1.0rc1`, with
corresponding engine-native tags `v0.1.0-rc.1`. Keep `[project].version` as the single
package metadata value; release tooling must set it to the calculated version
before building and verify that distribution metadata agrees.

| Change | During published `0.x` | From `1.0.0` onward |
| --- | --- | --- |
| Incompatible public contract change | Minor bump, with migration notes | Major bump, with migration notes |
| Compatible feature | Minor bump | Minor bump |
| Compatible fix or performance correction | Patch bump | Patch bump |
| Documentation, tests, or internal maintenance only | No automatic release | No automatic release |

The public compatibility surface comprises documented Python imports, callable
signatures, typed models and results; SQL function names, signatures and
behaviour; CLI options and exit semantics; configuration keys, defaults and
precedence; runtime-adapter and credential-provider contracts; and documented
ordering, shared-session, failure, cleanup and diagnostic guarantees.

Dropping a supported Python version or integration contract is a compatibility
change. Dependency updates are classified by their effect on supported consumers,
not simply by the dependency's own version number. Internal modules and private
SQL helpers are not public contracts merely because they can be imported or called.

Before the first publication, retain the existing single-current-API policy.
After publication, incompatible changes need the appropriate bump and migration
guidance even during `0.x`; this does not require compatibility shims. Move to
`1.0.0` through an explicit readiness decision when the project can support the
documented contracts, not automatically on the next breaking commit.

### Commit Classification

Use `feat` for compatible features and `fix` or `perf` for compatible corrections.
Mark any incompatible change with `!` or a `BREAKING CHANGE` footer and explain
the migration. Breaking classification takes precedence over commit type.
The highest required increment across the release range wins.

Configure and test the mapping explicitly: unmarked `refactor`, `docs`, `test`,
`build`, `ci`, and `chore` changes do not independently request a release. A
maintenance change that fixes an install/runtime defect must be classified as a
fix; an incompatible maintenance change must carry a breaking marker. Generated
release commits must not request another release.

Use an ancestry-preserving merge for promotion from `release/next` to `main`,
following the WebUI model. Do not squash away the candidate's feature/fix history.
Use a neutral promotion message such as `chore(release): promote Quackframe 0.1.0`;
the promotion itself must not request a second feature bump. Short-lived feature
and fix PRs may use the repository's normal merge convention, provided the final
history retains release classification and breaking-change information.

Apply one explicit commit-inclusion and classification policy to the release
gate, version engine and note generator. Qualifying merge messages participate,
including `feat`, `!` without a footer, a breaking footer without `!`, and both
breaking forms together. Do not let a message-level precheck include a merge
that the engine subsequently ignores. A qualifying merge whose child commits
are only ordinary fixes or maintenance must still receive its required bump
and retain its description and supplied migration guidance in the notes.

Neutral promotion and synchronization messages add no bump of their own.
Preserved feature/fix ancestry still participates in the appropriate release
range. Keep squash classification in the final message and footer; embedded
lists of earlier commit messages are not separately classified. Exclude work
already covered by reachable stable releases when considering new stable work;
candidate-only work must remain eligible for promotion. Synchronizing published
stable work into the candidate line must not replay it as a new candidate.

### Release Decision Contract

Determine the release flow before applying version-specific exemptions. The
workflow must establish it from trusted merge provenance and Git history.
A merge from `release/next` into `main` is a promotion even when its target is a
patch. Neither a patch-sized number nor a neutral commit message establishes
that the change is a direct stable fix. Missing promotion evidence must not
silently select the direct-patch path.

Read the merged PR's flow and explicit `Candidate:` selection before running
candidate-sensitive planning. Do not first select the newest reachable RC as a
precheck. An older published, accepted RC remains eligible when its ancestry,
stable target and exact tree match the promotion, even when a later RC exists
with a different tree. Missing, mismatched or unpublished selected candidates
must still fail; never silently substitute another candidate.

| Flow | Required evidence | Result |
| --- | --- | --- |
| First candidate | Qualifying change on `release/next`; bootstrap identities do not conflict | `0.1.0rc1`, followed by increasing RC revisions for qualifying updates |
| Later candidate | Qualifying new candidate work; latest stable ancestry synchronized | RC for the required target, preserving an existing target when the change does not require a larger bump |
| Promotion | Identified RC; ancestry and exact tree match; completed candidate publication; normal promotion acceptance | The RC's stable target with its suffix removed, including patch targets |
| Direct stable patch | Existing stable history; reviewed compatible fix on `main`; no candidate promotion; no feature/breaking increment in the release range | Next patch without requiring an RC |
| Maintenance or synchronization only | No new qualifying work and no outstanding release attempt being retried | No new version or publication |
| Retry | Existing release identity for the same source and flow | Reconcile that identity; do not allocate a replacement version |

The decision must identify the flow, source commit, tag, package version and,
for promotions, selected candidate tag and source. These are logical evidence
requirements, not a requirement to introduce a public API or a new framework.
Preparation and publication must consume that decision consistently. If either
recalculates it, verify agreement before emitting release metadata or publishing;
stamping one version after generating notes for another is unacceptable.

Local planning may operate without GitHub or PyPI credentials. Its output is a
proposal until the workflow verifies the required remote evidence. Unavailable
or conflicting evidence must stop automatic publication with an actionable
reason. A successful local plan or build is not publication authorization.

## Candidate, Promotion And Patch Flows

### First Candidate And Stable Release

Implement this before the intended first merge into `release/next`. Check remote
tags and PyPI history first: local metadata is not proof that a version is unused.
If history conflicts with `0.1.0rc1` or `0.1.0`, report the conflict rather than
silently selecting another initial version or overwriting release identity.

The first qualifying merge publishes `0.1.0rc1`; subsequent qualifying changes
produce `0.1.0rc2`, `0.1.0rc3`, and so on until stable promotion publishes `0.1.0`.
Do not calculate an unintended `0.2.0` or `1.0.0` from all pre-release development
history. Bootstrap the initial notes from reviewed delivered behaviour without
inventing a previous release tag. Before the first stable publication, fixes
belong in this candidate flow; there is no published stable line to patch yet.

The `0.1.0` bootstrap target applies to candidate calculation, every subsequent
bootstrap RC, first stable promotion, note generation and package stamping.
It must survive fix-only and performance-only history as well as feature or
breaking history. Do not force only the first candidate and then let first
stable calculation fall back to `0.0.1`.

Initial candidate notes must explain the reviewed delivered behaviour; a generic
`Initial Release` placeholder does not satisfy this requirement. Initial stable
notes must retain that explanation and any supplied migration guidance. Use
explicit template configuration or a reviewed initial summary, and assert note
content in tests. Do not fabricate an earlier release to make generation work.

### Automatic Candidates

1. Review and merge features or candidate fixes into `release/next`.
2. CI validates the exact merged source and release tooling analyses qualifying
   changes against the branch's release history. Maintenance-only changes and
   generated release commits must not create an endless series of RCs.
3. Calculate the candidate version, prepare metadata and notes, build with
   Hatchling, and automatically publish the verified RC to PyPI. Mark its GitHub
   release as a prerelease. No manual workflow start or metadata-only PR is required.
4. Install the exact RC version in a representative consuming project and record
   acceptance evidence. Python's RC version suffix carries prerelease identity;
   do not copy npm distribution tags into the PyPI design.

### Stable Promotion

1. Freeze the candidate commit and RC version, included changes, migration notes,
   validation results and any accepted limitations.
2. Review a promotion PR from `release/next` to `main`. Its description identifies
   the tested candidate and expected stable version, including `0.1.0` initially.
3. If either branch changes in a way that changes the candidate, refresh the
   candidate evidence and review. Do not publish untested intervening changes.
4. Merge after normal protection and release acceptance. The trusted pipeline
   validates and automatically publishes the stable version, removing the RC
   suffix without adding another minor bump for the same feature history.
5. Synchronize `main` back into `release/next` through the normal reviewed process
   before the next cycle. A synchronization-only merge must not create a release
   by reclassifying already published changes as new work.

Every promotion must verify the following before creating its stable tag or
uploading stable distributions:

- The selected RC tag resolves to the recorded candidate source, is reachable
  through the promotion's preserved ancestry, and targets the intended stable
  version. Validate against that candidate; missing evidence must not silently
  substitute another RC.
- The promoted source tree exactly matches the candidate tree. This applies to
  minor, major and patch targets and includes documentation, configuration and
  workflow files. Compare source trees before generated version stamping.
- The candidate has a completed GitHub prerelease with retained, verifiable
  source/version records and artifact checksums. Both expected distributions
  are present on PyPI and their hashes match the retained candidate artifacts.
  A tag, a draft, a local build, or a partial upload alone is insufficient.
- The promotion PR records consuming-project acceptance of that exact published
  candidate. This remains part of normal promotion review; it does not add a
  manual gate to automatic RC or direct-patch publication.

An API error, inaccessible release evidence, conflicting source, or mismatched
artifact hash is a verification failure. Do not treat it as evidence that the
candidate completed publication. This check concerns the selected candidate
only; the orphan-tag rule in [Publication And Recovery](#publication-and-recovery)
still permits a later qualifying version to publish.

### Stable Patches

After `0.1.0` exists, a compatible fix PR can target `main` directly. Successful
validation after merge automatically publishes the next patch, such as `0.1.1`.
There is no separate RC or promotion stage for this path. Merge the stable fix
back into `release/next` so the candidate line does not lose it.

The direct-patch exemption applies to this flow, not every calculation whose
patch component increases by one. A `release/next` promotion targeting, for
example, `0.1.1rcN` to `0.1.1` must satisfy all promotion requirements above.

Keep version histories branch-aware: if `main` publishes `0.1.1` while the next
feature candidate is `0.2.0rcN`, synchronization must preserve that upcoming
minor target. Include the fix in subsequent candidate testing without replaying
it as a new stable bump. A stable fix that changes the frozen candidate requires
renewed candidate validation before promotion.

## Publication And Recovery

Trigger publication automatically from trusted `release/next` and `main` merges
for the branch-specific flows above. Other branches and PR validation runs must
not publish. Verify branch, merge identity and release classification; a label,
commit prefix or arbitrary version-file change alone must not authorize upload.
Validate the exact source and associate every artifact with its commit and version.

Generated metadata is applied only in the isolated build checkout. No generated
bump commit is pushed, so no protected-branch bypass is needed. The tag records
the tested source commit; `release.json` records its package version. Retained
distributions carry that stamped version and generated notes live in the GitHub
release assets. Source `[project].version` remains a development baseline, not
an assertion of the latest published version.

Run publication as dependent jobs in the same trusted workflow, or through an
explicitly invoked reusable workflow. Do not rely on an automatically pushed
tag starting another workflow: GitHub token-generated events have trigger
restrictions. Promotion-PR CI must also be demonstrated with the chosen token and
repository settings; document any required workflow approval or scoped App token.

After validation, build the wheel and source distribution once using Hatchling,
inspect their metadata and contents, and smoke-test the wheel outside the source
checkout in a clean Poetry-managed consumer. Check that the source distribution
can also build a usable wheel. Retain the original publication artifacts and
their checksums; do not rebuild them in the upload job.

Create the version tag at the exact validated release source and prepare a draft
GitHub release. Upload the retained distributions using the protected PyPI job.
Verify PyPI version, file hashes and installed-package behaviour, then publish
the GitHub release with the matching changelog and artifact identity. Package
publication and GitHub release completion are separate recorded states.

Serialize release calculation and publication appropriately. Never allow two
runs to allocate or upload the same version concurrently, and do not cancel an
upload halfway through merely because another request arrived.

Release history follows Git tags, as in MAD.Prefect and WebUI. A successfully
created remote tag reserves its version even if subsequent publication fails.
If draft creation fails before a GitHub draft exists, a later qualifying change
may publish a newer version using that tag as history. The earlier version can
remain unpublished; publishing a newer version does not repair it automatically.
An orphaned tag alone must not block later publication or cause its version to
be reused. Quackframe's separate guard for an incomplete GitHub draft still
requires recovery before another publication.

Retries of the same version reconcile remote state before writing. An existing
tag must point to the expected commit, and existing PyPI files must match retained
artifact hashes. A matching completed release is a no-op; conflicting identity
stops the retry. Resume partial uploads only for missing artifacts with verified
matching state. If artifacts are lost or identity cannot be established, stop
that retry for maintainer recovery rather than blindly skipping duplicate files
or replacing a version. This does not require scanning all earlier tags and
blocking newer versions until every earlier publication is complete.

Document recovery from tag creation, partial upload, verification failure, and
GitHub release failure independently. Never move a published tag or reuse a
published version for different bytes. A defective package needs a corrected
release; yanking, when appropriate, is a separate maintainer decision. Report
failure truthfully even if some publication steps have already succeeded.

### Publication States And Allowed Recovery

Track version reservation, retained evidence, PyPI upload and GitHub completion
separately. Reconcile the attempted version's actual remote state before each
write; the existence of one record must not imply the others exist.

Authorization, retention and finalization must look up both draft and published
releases through GitHub's paginated release listing, using the existing token's
push access. The `releases/tags/{tag}` endpoint returns published releases and
cannot establish that a draft is absent. Keep that endpoint only where completed
publication is required, such as promotion-candidate verification. Missing or
ambiguous records and failed reads must stop recovery before any write.

Regression responses must follow the
[GitHub release API contract](https://docs.github.com/en/rest/releases/releases):
drafts appear in an authorized release listing, while their published-by-tag
lookup returns 404. Exercise initial finalization, partial-upload retries and
completed retries through the workflow entrypoints with those responses.

| State of the attempted version | Allowed recovery or next step | Eligible as a promotion candidate? |
| --- | --- | --- |
| No remote tag | Prepare and validate; rebuilding is allowed before reservation | No |
| Tag exists, draft absent | Preserve reservation; restore exact original evidence/assets through reviewed recovery when available; do not rebuild that version | No |
| Draft or assets incomplete | Restore missing original assets only with proven identity; otherwise stop for recovery | No |
| Complete retained bundle, PyPI files absent or partial | Verify existing hashes; upload only missing original distributions | No |
| Both PyPI files verified, GitHub release still draft | Finalize the matching GitHub release; do not upload again | No |
| Completed GitHub release and matching PyPI files | Same-version retry is a no-op after verification | Yes, if the ancestry, tree and normal acceptance requirements also pass |
| Source, version or artifact identity conflicts | Stop this attempt; do not overwrite, move tags or silently skip conflicts | No |

An incomplete draft continues to block a later publication. A reserved tag with
no draft does not block a newer qualifying version and must not be reused. Thus
advancing past an orphan and promoting that orphan are different decisions:
the former is permitted; the latter lacks completed candidate evidence.

## External Setup

- Verify ownership or availability of the `quackframe` PyPI project and configure
  a Trusted Publisher for the exact repository, workflow and environment.
- Protect both `main` and `release/next` with review and required validation.
  CI validates both release branches and the PRs targeting them.
- Give the package job `contents: write` to discover and download draft releases.
  Give tagging/release jobs repository-scoped App tokens with `contents: write`
  and `workflows: write` so candidates can include workflow changes. Configure
  the App client ID and private key as described in the release guide; branch
  protection bypass is unnecessary. Only the PyPI upload job gets
  `id-token: write`. Untrusted PR code must not receive publishing authority.
- Apply the agreed merge-triggered publication model without adding a routine
  manual RC or patch approval step. Record the maintainers or GitHub team that
  can approve candidate promotion, stable fixes and recovery. Configure any
  protected publishing environment to support this agreed automation.
- Rehearse without production credentials. TestPyPI is optional and requires
  its own project/publisher setup; it must not be mistaken for production proof.

## Implementation Deliverables

- [x] Add a developer-facing versioning and release guide, linked from the docs
  index and `CONTRIBUTING.md`; update applicable agent guidance.
- [x] Verify the release tool against candidate, promotion and patch
  histories; add it and build/verification tools through Poetry. Configure the
  version provider, explicit bump rules and durable notes, preserving Hatchling.
- [x] Implement automatic RC, stable promotion and direct patch workflows
  with the smallest necessary helper code and focused tests.
- [x] Establish the commit classification, candidate freshness checks, first-release
  bootstrap, concurrency rules and retry behaviour described above.
- [ ] Satisfy the acceptance scenarios below, with persistent regression tests
  for the five confirmed findings and evidence from the actual workflow paths.
- [ ] Configure and verify GitHub/PyPI settings with repository-owner authority.
- [x] Complete a non-publishing rehearsal and document operational commands and
  recovery examples. Record the first authorized production verification separately.

## Validation And Acceptance

### Required Scenarios

Use these IDs to map scope requirements to persistent repository tests and,
where necessary, hosted evidence. Each row must have named tests or an explicit
unverified status. The cases within a row are required variants, not a choice
of one representative example. Use real temporary Git histories for version
calculation and merge behaviour, with actual file changes for tree checks.

| ID | Initial state and trigger | Required outcome and assertions |
| --- | --- | --- |
| REL-01 | No tags; separately use feature-only, fix-only, perf-only and breaking history, then another qualifying update and promotion | `0.1.0rc1` -> `0.1.0rc2` -> `0.1.0`; preparation, notes, tag and package metadata agree at every step (BUG-002). |
| REL-02 | Bootstrap identities already reserved or conflicting | Preserve matching identity for retry; reject conflicting identity; never silently reuse or choose a different bootstrap target. |
| REL-03 | Stable `0.1.0` and `1.0.0`; ordinary commits and merges with `feat`, `!` alone, footer alone, both forms and mixed ranges | Highest required bump wins; breaking changes require minor during `0.x`, major during `1.x`; test merges whose children are only fixes or maintenance; retain feature/migration text (BUG-003). |
| REL-04 | Maintenance-only history, generated release messages, neutral promotion and synchronization; normal squash messages | Maintenance creates no version; neutral merges do not add a bump; preserved qualifying ancestry and the final squash classification still count. |
| REL-05 | Identified published RC promoted to each of a patch, minor and major target; matching source tree | Publish the exact stable target without an additional bump; retain candidate/source identity. |
| REL-06 | Each REL-05 case with a later documentation change, code change, workflow change or differing merge resolution | Reject promotion before stable tagging/upload; a newly published matching candidate restores eligibility; patch targets receive the same checks (BUG-006). |
| REL-07 | Selected RC has tag only, incomplete draft, partial upload, completed matching publication, conflicting evidence, or an evidence-read error | Only completed matching publication passes the remote gate; failures never fall back to direct-patch eligibility (BUG-005). |
| REL-08 | Existing stable line; direct `fix`/`perf` PR, with an unrelated next-minor RC in parallel | Next stable patch is allowed without an RC; direct feature/breaking work cannot use that exemption. |
| REL-09 | `0.2.0rcN` exists while `main` publishes `0.1.1`; synchronize the changed stable tree | Reject stale stable ancestry; sync alone creates no RC; changed tree cannot promote; a subsequent qualifying candidate retains `0.2.0` and includes the fix. |
| REL-10 | Initial feature and fix descriptions plus supplied migration guidance; prepare initial RC and stable, then subsequent releases | Retained notes explain delivered behaviour and migration; assert content and version identity, not file existence or a generic initial placeholder (BUG-004). |
| REL-11 | Wrong branch, failed CI, PR event, untrusted repository, superseded source, or manual version-file edit alone | No publication; build/upload source must be the qualifying validated source; metadata edits alone cannot authorize a release. |
| REL-12 | Failure before tagging; failure after tagging but before draft creation; then a newer qualifying change | Before reservation rebuilding is allowed; reserved version is never reused; newer version may publish when no draft blocks it; the orphan cannot serve as a completed promotion candidate. |
| REL-13 | Failure during draft/asset retention or during PyPI upload; retry with absent, wheel-only, sdist-only or complete PyPI files | Preserve original source and bytes; incomplete drafts block newer publication; resume only missing files; conflicting or lost identity stops recovery. |
| REL-14 | Upload verified but finalization fails; then same-version retry and completed retry | Finalize without rebuilding/reuploading; a completed matching retry makes no publication changes and does not allocate a version. |
| REL-15 | Duplicate triggers and overlapping stable/candidate publication requests | Serialize allocation through completion without cancelling an upload; preserve each flow's identity; no duplicate allocation or artifact replacement. |
| REL-16 | Prepared package from the exact source | Build wheel from sdist; verify contents, versions and checksums; clean Poetry consumer runs Python/CLI ordered SQL, shared-session and fail-fast checks without Prefect. |
| REL-17 | Retained draft appears in the authorized paginated listing but returns 404 by tag; missing, ambiguous or unreadable release evidence | Finalize a new draft and resume original artifacts on retry; a completed retry is a no-op; failed evidence never authorizes writes (BUG-007). |
| REL-18 | Accepted RC1, changed RC2 for the same target, promotion tree restored exactly to RC1; PR explicitly selects RC1 | Resolve provenance first and honor RC1 through planning, preparation and publication checks; selecting mismatched RC2 or a missing RC still fails (BUG-008). |

Pair interacting cases explicitly: fix-only bootstrap with stable note generation;
qualifying merge messages with patch exemptions; patch promotions with changed
trees; and orphan-tag advancement with rejection of that orphan as a promotion
candidate. Testing either side of these pairs alone is insufficient.

### Evidence Required Before Acceptance

Before implementing each confirmed fix, add its persistent regression test and
record that it fails for the documented defect. After the fix, keep it alongside
the valid neighbouring case: direct patches remain allowed, matching promotions
still succeed, and later releases remain possible after orphaned tags.

Exercise classification, planning, preparation and workflow authorization
together. Local workflow tests must execute the actual scripts/guards used by
the workflow with controlled GitHub/PyPI responses, including error responses;
assert permitted and prohibited writes. Do not duplicate the intended guard in
a test and leave the actual workflow path untested. Check the decision's source,
flow, selected candidate, version, notes and artifact identity across boundaries.

Review the expected outcomes against this scope before using test success as
evidence of correctness. A passing helper test or aggregate test count does not
substitute for a scenario's missing assertions. Any behaviour fix discovered in
review must extend the applicable regression coverage before that finding is
closed. Preserve the accepted orphan-tag behaviour when adding recovery checks.

Record the reviewed revision, named tests for each scenario ID, actual results
and remaining gaps. Keep local simulation separate from hosted verification.
Hosted evidence must cover token-trigger behaviour, required checks,
least-privilege permissions, environment/ref restrictions, source selection,
concurrency, draft recovery and PyPI OIDC. Retain optional-integration checks and
document the supported Python/platform matrix and its gaps. Missing hosted
evidence remains unverified even when local workflow simulations pass.

Run focused release tests followed by the repository's standard checks:

```powershell
poetry run pytest
poetry run ruff check .
poetry run pyright
python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

Also run formatting, workflow validation and distribution checks introduced by
the implementation. Repository readiness requires all locally testable scenarios
above to pass, known release defects to have passing regressions, and any check
failures or environment limits to be reported explicitly. The phase is complete
only when policy, implementation, tests, operator documentation, authorized
external setup and an authorized first publication are verified end to end.
If hosted work is deferred, record local evidence and the outstanding hosted
scenarios separately and leave the phase open.

## Implementation Readiness

The initial versions, release branches, automatic RC publication, promotion
model, direct patch path, Poetry and Hatchling are agreed. The repository workflow
is disabled until `QUACKFRAME_RELEASES_ENABLED=true`; the release guide lists
external setup. No commit, push, branch creation, tag or package publication is
part of local implementation validation.

Remote inspection on 2026-10-02 found no release tags, no `release/next` branch,
and a 404 from the PyPI `quackframe` package endpoint. These checks do not reserve
the package name or configure its publisher. Protect the branches and configure
the GitHub `pypi` environment and PyPI Trusted Publisher before activation.

Local validation on 2026-10-02:

- All 21 focused release and artifact tests passed, including bootstrap, RC
  increments, stable promotion, parallel patches, synchronization and retries.
- A temporary checkout calculated and stamped `0.1.0rc1`, generated notes,
  built the source distribution and then its wheel through Hatchling, passed
  Twine checks, and sealed and verified distribution metadata and hashes.
  Installation into a clean Poetry consumer passed Python and CLI execution,
  shared-session and fail-fast checks without Prefect. Nothing was published.
- Full pytest: 414 passed, four expected failures, and one subprocess timeout
  in the existing optional-backend isolation test. All three parametrizations
  of that test passed on an isolated rerun. This is not a clean full-suite result.
- Poetry lock validation, Pyright, scoped Ruff lint and formatting, documentation
  links, and `git diff --check` passed. Poetry reports the existing license-table
  deprecation warning. Repository-wide Ruff reports 13 existing findings in
  the `MAD.Utilities.DuckDB` prototype; those unrelated files were left unchanged.
- GitHub workflow syntax was checked with actionlint 1.7.12, suppressing only
  its unsupported-key warning for GitHub's documented `concurrency.queue` field.
  The queue setting was checked against current GitHub documentation. Actual hosted runs,
  environment restrictions, token permissions and PyPI OIDC remain unverified
  until external setup and activation.

Review corrections on 2026-10-05 give draft recovery the required Contents write
permission and use short-lived, current-repository GitHub App tokens for tag and
release writes, including finalization when candidate workflows differ from the
default branch. App installation and hosted permission verification remain part
of external activation.

Validation of these corrections: full pytest passed with 416 passed and four
expected failures. Scoped Ruff lint and formatting, Pyright, documentation links,
and `git diff --check` passed. Repository-wide Ruff still reports the 13 existing
prototype findings. Actionlint 1.7.12 passed with only its outdated schemas for
`concurrency.queue` and the App action's `client-id` input suppressed; those fields
were checked against GitHub's current documentation and the v3 action metadata.
Hosted draft recovery and workflow-changing candidate publication remain untested.

Subsequent holistic review on 2026-10-05 confirmed five unresolved defects:
fix-only stable bootstrap, qualifying merge classification, initial note content,
publication proof for the selected RC, and patch-promotion tree checks. The
earlier passing tests and package rehearsal did not cover those failures.
Implementation deliverables above are reopened pending their regression tests
and the acceptance evidence specified here. The strengthened scope does not
mark any implementation fix as complete.

The latest full-suite review run recorded 416 passed, three expected failures
and one failure in the unchanged unprotected fsspec/Paramiko diagnostic
(`Garbage packet received`); its isolated rerun produced the expected
deadlock-related xfail. This was not a clean full-suite result and does not
supersede the need to validate the eventual release fixes.

The phase remains In Progress until local defects and acceptance gaps are
resolved, followed by authorized external activation and a verified first
production publication.

## Regression Fix Evidence, 2026-10-05

The fixed implementation keeps one immutable release decision through planning,
preparation, retention and finalization. The decision includes flow and selected
candidate identity. The workflow verifies merged-PR provenance and the candidate
named in the promotion PR before checking completed GitHub/PyPI publication.
All remote reads fail closed. Direct patches and advancement past orphaned tags
remain separate, supported paths.

Before implementation, the existing 16 release-history tests passed while 16
new parametrized cases failed for BUG-002, BUG-003, BUG-004 and BUG-006. The
actual original Bash draft guard also failed its new tag-only promotion test
for BUG-005. No remote writes were made. These failures preceded changes to
the planner and parser settings. The workflow regression now executes the
replacement Python entrypoints named in the YAML with controlled GitHub/PyPI
responses; it does not reimplement their guards in test code.

Review added failing regressions before correcting retained version identity,
missing finalization reservations, cross-job source/tag agreement and conflicting
GitHub prerelease metadata. These extend the existing evidence requirements.

Persistent tests are in [release histories](../../../tests/test_release.py),
[workflow paths](../../../tests/test_release_workflow.py) and
[artifact checks](../../../tests/test_release_artifacts.py). The coverage map is:

| Scope | Named local evidence | Remaining boundary |
| --- | --- | --- |
| REL-01 | `test_bootstrap_through_second_candidate_and_stable` covers feat/fix/perf/breaking history, both RCs, stable, notes and metadata. | Production bootstrap identity must still be checked before activation. |
| REL-02 | `test_bootstrap_rejects_conflicting_tag_history`, `test_retry_resumes_original_version`, `test_preparation_rejects_changed_decision_and_reserved_rebuild`, `test_retry_evidence_failure_allows_no_publication_writes`. | Remote states are simulated. |
| REL-03 | `test_qualifying_merge_cannot_escape_as_direct_patch`, `test_ordinary_commit_classification_and_mixed_range`: both stable eras, every breaking form, features, fixes, perf, fix-only and maintenance-only merge children, note content. | None for the specified local classification cases. |
| REL-04 | `test_maintenance_and_squash_body_do_not_authorize_release`, `test_candidate_promotion_patch_and_concurrent_next_minor`, `test_synchronization_cannot_resume_an_already_promoted_rc`. | Actual repository merge settings require hosted verification. |
| REL-05/06 | `test_promotion_target_and_freshness`: patch/minor/major, matching trees, docs/code/workflow/merge-resolution changes, rejection and refreshed candidates; `test_selected_candidate_is_not_silently_substituted`. | Publication acceptance remains normal PR review. |
| REL-07 | `test_tag_only_candidate_cannot_authorize_stable_publication`: tag only, draft, partial upload, complete, conflicting source/hash, GitHub/PyPI read errors. | Live API permissions and publication states remain unverified. |
| REL-08/09 | `test_candidate_promotion_patch_and_concurrent_next_minor`, `test_patch_provenance_cannot_silently_fall_back`, classification and freshness tests above. | Hosted simultaneous branch runs remain unverified. |
| REL-10 | Bootstrap tests, `test_initial_candidate_and_stable_notes_describe_delivery`, ordinary/merge classification and promotion tests assert delivered descriptions, migration text, version and source. | None for local note rendering. |
| REL-11 | `test_workflow_eligibility`, `test_version_file_edit_alone_does_not_release`, `test_retention_rejects_bundle_for_another_workflow_identity`. | GitHub event delivery and branch protections remain unverified. |
| REL-12 | `test_new_candidate_after_orphan_respects_draft_guard`, `test_tag_reservation_failure_cannot_rebuild_on_retry`, preparation and candidate-publication tests. | Maintainer restoration of original remote assets remains a hosted rehearsal. |
| REL-13/14 | `test_retry_upload_and_finalization_preserve_identity`, `test_retry_evidence_failure_allows_no_publication_writes`, `test_finalization_cannot_create_missing_reservation`, `test_retry_rejects_conflicting_github_release_identity`, artifact tests. | Actual PyPI upload and GitHub finalization are simulated. |
| REL-15 | `test_workflow_serializes_and_gates_writes` checks YAML wiring; retry tests prove no duplicate reservation, upload staging or finalization writes. | Actual queued concurrent Actions execution remains unverified. |
| REL-16 | Isolated updated-source rehearsal built an sdist and its wheel, passed Twine, metadata and checksum verification, and ran `scripts/package_smoke.py` in a clean Poetry consumer without Prefect, including Python/CLI fail-fast checks. | Local Windows/Python 3.13 evidence; hosted Linux and the complete supported Python/platform matrix remain unverified. |

The source checkout remains uncommitted on `feat/setup`; the reviewed base is
`2662b93c4a68fce91999e5cd5ba073d083972e8a`. The user-owned staged changes were
preserved. The SHA-256 fingerprint of the final release implementation and tests
is `38f6fd48ebd44ff88e8f1c01a47eea5ff5246d31faf5d4dc400cad9c5e8a7cb0`.
It hashes sorted repository-relative paths, a NUL separator and raw file bytes
for `pyproject.toml`, `.github/workflows/release.yml`, `scripts/*.py` and
`tests/test_release*.py`.

Local validation:

- The final full suite passed **517 tests with four expected failures**, including
  all **122 release tests**. The expected failures are the existing unprotected
  upstream SFTP deadlock diagnostics. This run used Windows/Python 3.13.9 with
  verbose output and a 60-second diagnostic stack dump, and took 22 minutes.
  An earlier full run was interrupted after extended periods without visible
  progress; the diagnostic rerun completed successfully on the final source.
  The earlier expanded acceptance run passed 112 tests, and the final workflow
  subset independently passed all 37 cases.
- The final source distribution and its wheel passed Hatchling build, Twine,
  distribution metadata and checksum checks, and the clean Poetry consumer's
  Python/CLI ordering, shared-session and fail-fast tests without Prefect.
- Pyright reported zero errors or warnings. Scoped Ruff and formatting,
  documentation links, Poetry lock validation and `git diff --check` passed.
  Repository-wide Ruff reports the same 13 findings in the unchanged prototype.
  Poetry retains the existing license-table deprecation warning; the clean
  consumer's older pkginfo warns about metadata 2.5 but installs successfully.
- Actionlint 1.7.12 passed with only its obsolete `concurrency.queue` and App
  `client-id` schema diagnostics excluded. Those settings were rechecked against
  the linked GitHub concurrency documentation and
  [v3 action metadata](https://github.com/actions/create-github-app-token/blob/v3/action.yml).

The phase stays **In Progress**: local simulations and a distribution rehearsal
do not establish hosted permissions, protected-environment behavior, token
triggering, concurrency or PyPI OIDC readiness.

## Draft Recovery And Candidate Selection Corrections, 2026-10-05

BUG-007 and BUG-008 are fixed locally. Authorization, retention and finalization
now share a draft-inclusive paginated release lookup. Candidate publication
verification still requires the published-by-tag endpoint. Workflow planning
reads the merged PR's flow and explicit candidate before invoking the planner.

The remote test double now follows GitHub's documented distinction between
draft-inclusive listings and published-by-tag lookup, with separate response
pages. Before these fixes, four partial/completed upload retry cases, initial
draft finalization and the accepted older-candidate case failed: **six failed,
two rejection controls passed**. After the fixes, all **52 workflow cases pass**.

| Scope | Persistent evidence |
| --- | --- |
| REL-13/14/17 | `test_new_release_finalizes_retained_draft` exercises initial finalization with the draft on a later listing page and a completed no-op retry; the four `test_retry_upload_and_finalization_preserve_identity` cases exercise absent, wheel-only, sdist-only and complete PyPI state. |
| REL-17 | `test_draft_lookup_failure_prevents_writes` covers missing, unreadable and ambiguous records during authorization, retention and finalization. |
| REL-18 | `test_workflow_uses_explicit_candidate_before_planning` carries the accepted older RC through planning, preparation and retention; mismatched and missing selections still fail. |
| REL-04 | `test_workflow_maintenance_is_no_release_after_provenance` preserves no-release behavior on both branches after moving provenance ahead of planning. |

The full suite passed **532 tests with four expected upstream SFTP failures**
in 21 minutes 53 seconds, including all **137 release tests**. The workflow
subset, scoped lint/formatting, type checking, lock validation, documentation
links and `git diff HEAD --check` pass. Repository-wide Ruff still reports the
13 existing findings in the unchanged prototype.

The corrected implementation fingerprint is
`4933d74ba8a5cfdc8d56e118c9457ac3a9a1f98dd9c93fd044e7ef53b92b6df3`,
using the same file set and SHA-256 procedure recorded above. It supersedes the
earlier implementation fingerprint for these two corrections.

The phase remains **In Progress**. The user requested these local fixes before
the next acceptance step; no hosted setup, rehearsal or publication is included.

## Related Docs And Implementation References

- [Documentation Index](../../README.md): developer and implementor navigation.
- [Developer API](../../developer-api.md): public Python and CLI contracts.
- [Execution Lifecycle](../../execution-lifecycle.md): execution guarantees.
- [Configuration](../../configuration.md): configuration compatibility surface.
- [SQL Function Extensions](../../python-extensions.md): SQL extension contracts.
- [Runtime Adapters](../../runtime-adapters.md): optional adapter boundaries.
- [Credential Providers](../../credential-providers.md): provider contracts.
- [Release Guide](../../releases.md): implemented workflow, setup and recovery.
- [MAD.Prefect release workflow](https://github.com/maitdevptyltd/MAD.Prefect/blob/main/.github/workflows/publish.yml):
  reference for recording a version and tag before downstream publication.
- [WebUI release tools v2.0.2](https://dev.azure.com/maitdevptyltd/WebUI/_git/webui.release.tools?path=/src/doctor/runner.ts&version=GTv2.0.2):
  reference for checking the proposed tag and allowing a newer version after a
  failed publication, without requiring recovery of every earlier tagged version.
- [Python Semantic Release](https://python-semantic-release.readthedocs.io/en/stable/):
  branch-aware release engine and version calculation.
- [GitHub workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow):
  token-generated events and release-PR workflow execution.
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): identity
  configuration for package upload without a long-lived PyPI token.
