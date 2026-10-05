# Release Review Findings

Record unresolved bugs requiring implementation here for resolution in one pass.
Exclude implemented fixes and intended behaviour from the active bug list. Keep
reclassified findings separately below so rejected requirements are not
reintroduced. Merge duplicates and keep each finding's status, evidence, and
validation expectations explicit.

## Current Status

BUG-002 through BUG-008 are resolved locally with persistent regression coverage.
The historical reproductions below explain what the tests protect; they describe
the pre-fix implementation. BUG-001 remains intended orphan-tag behaviour.

The [release scope](docs/epics/05-releases/01-semantic-versioning-and-publication.md#draft-recovery-and-candidate-selection-corrections-2026-10-05)
records scenario-to-test coverage, local validation and remaining hosted checks.
The phase remains In Progress because GitHub/PyPI activation and a first
production publication have not been verified.

| Finding | Persistent regression | Resolution |
| --- | --- | --- |
| BUG-002 | `test_bootstrap_through_second_candidate_and_stable` | Bootstrap decision stays at `0.1.0` through candidates, preparation and stable promotion. |
| BUG-003 | `test_qualifying_merge_cannot_escape_as_direct_patch` | Planner, version engine and notes share merge-inclusive commit parsing. |
| BUG-004 | `test_initial_candidate_and_stable_notes_describe_delivery` | Unmasked notes describe delivery since stable under the exact planned version. |
| BUG-005 | `test_tag_only_candidate_cannot_authorize_stable_publication` | Actual workflow entrypoints require completed matching GitHub/PyPI evidence for the identified RC. |
| BUG-006 | `test_patch_promotion_cannot_include_changes_after_candidate`, `test_promotion_target_and_freshness` | Flow and candidate identity precede the direct-patch exception; all promotions require exact trees. |
| BUG-007 | `test_new_release_finalizes_retained_draft`, `test_retry_upload_and_finalization_preserve_identity`, `test_draft_lookup_failure_prevents_writes` | Draft-inclusive paginated lookup supports finalization and retries; missing, ambiguous or unreadable evidence prevents writes. |
| BUG-008 | `test_workflow_uses_explicit_candidate_before_planning`, `test_workflow_maintenance_is_no_release_after_provenance` | Trusted PR flow and explicit candidate selection precede planning; maintenance remains a no-op. |

Tests live in [release histories](tests/test_release.py),
[workflow simulations](tests/test_release_workflow.py) and
[artifact verification](tests/test_release_artifacts.py).

Before the two workflow corrections, local validation had 517 passed and four
expected upstream SFTP failures, including all 122 release tests. Type checking,
scoped lint/formatting,
documentation links, workflow validation and the distribution/clean-consumer
rehearsal passed. The 13 existing prototype lint findings and hosted publication
verification remain outside these resolved release bugs.

The corrected workflow subset passes all 52 cases. Its pre-fix run had six
failures and two passing rejection controls. The final full suite passed
**532 tests with four expected upstream SFTP failures**, including all **137
release tests**, in 21 minutes 53 seconds. Type checking, scoped lint/formatting,
lock validation, documentation links and `git diff HEAD --check` pass. Hosted
acceptance remains deferred.

## Resolved Findings

### BUG-007: Draft recovery uses the published-release endpoint

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Priority:** P1.
- **Location:** [Release workflow helper](scripts/release_workflow.py),
  authorization, retention and finalization.
- **Pre-fix evidence:** After correcting the remote test double to match GitHub,
  all four `test_retry_upload_and_finalization_preserve_identity` cases and
  `test_new_release_finalizes_retained_draft` failed. The workflow looked up
  drafts through `releases/tags/{tag}`, which only exposes published releases,
  and interpreted 404 as missing retained evidence. Normal finalization could
  fail after PyPI upload, leaving a draft that blocked later releases.
- **Resolution:** Look up retained releases through the authorized paginated
  listing, including drafts. Keep published-by-tag lookup for promotion evidence.
  Missing, ambiguous and unreadable retained records still prevent writes.
- **Contract evidence:** [GitHub release endpoints](https://docs.github.com/en/rest/releases/releases)
  document draft visibility in listings and published-by-tag lookup.
- **Acceptance:** Scope scenarios REL-13/14 and REL-17; initial finalization,
  partial-upload recovery, completed no-op retries, pagination and failed reads
  must use the actual workflow entrypoints.

### BUG-008: Preliminary planning ignores the selected candidate

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Priority:** P2.
- **Location:** [Release workflow helper](scripts/release_workflow.py),
  `workflow_plan()`.
- **Pre-fix evidence:**
  `test_workflow_uses_explicit_candidate_before_planning[accepted]` failed after
  publishing RC1 and a changed RC2, restoring RC1's exact tree, and selecting RC1
  in the promotion PR. The preliminary implicit plan validated RC2 before the PR
  selection was read. The mismatched and missing selection controls rejected
  publication as expected.
- **Resolution:** Read trusted PR provenance and its candidate selection before
  planning. Honor the identified candidate through preparation and retention;
  maintenance-only direct/candidate work still produces no release.
- **Acceptance:** Scope scenario REL-18; the matching selected RC succeeds while
  a mismatched or missing selection still fails before publication writes.

### BUG-002: A fix-only bootstrap cannot reach its first stable release

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Pre-fix evidence:** independently reproduced in the latest holistic review on
  2026-10-05. Fix-only history produced `0.1.0rc1` and `0.1.0rc2`, then failed
  stable promotion. No package was published.
- **Priority:** P2 — first stable publication is blocked for fix-only history.
- **Location:** [scripts/release.py](scripts/release.py), `plan()` version
  calculation and first-release validation.
- **Design requirement:** [First Candidate And Stable Release](docs/epics/05-releases/01-semantic-versioning-and-publication.md#first-candidate-and-stable-release)
  requires the bootstrap sequence to target `0.1.0rcN`, then `0.1.0`, regardless
  of the pre-release development history.

### Trigger and observed code path

1. Start with no release tags and only qualifying `fix` changes.
2. Release from `release/next`. The bootstrap override produces `0.1.0rc1`.
3. Promote that candidate to `main` without changing its tree.
4. Stable version calculation no longer applies the bootstrap override and
   calculates `0.0.1` from the fix-only history.
5. First-release validation rejects that result instead of publishing `0.1.0`.

### Impact

A valid first candidate cannot become the first stable release despite following
the agreed promotion process.

### Suggested resolution

Preserve the explicit `0.1.0` bootstrap target through first stable promotion,
including release preparation and generated metadata. Keep the requirement for
a matching candidate and preserve normal direct stable patch publication after
the first stable release exists.

### Validation expectation

Add an isolated-history regression test covering fix-only bootstrap through
`0.1.0rc1` and promotion to `0.1.0`. Verify preparation stamps `0.1.0` and produces
consistent release notes and metadata. Retain coverage for candidate freshness,
feature-led bootstrap, and subsequent direct stable patches such as `0.1.1`.

### BUG-003: Feature and breaking merge commits can be classified as stable patches

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Pre-fix evidence:** independently reproduced again in the latest holistic review
  on 2026-10-05, including all four merge-message variants below during `0.x`
  and a breaking merge during `1.x`. Planning and preparation were exercised;
  no package was published.
- **Priority:** P1 — features and incompatible changes can bypass RC promotion,
  receive a stable patch version, and lose their merge-message descriptions
  from release notes.
- **Location:** [pyproject.toml](pyproject.toml), lines 108–111 (commit parser
  options), and [scripts/release.py](scripts/release.py), lines 97–106
  (classification and version calculation) and 123–130 (patch exemption).
- **Design requirement:** [Commit Classification](docs/epics/05-releases/01-semantic-versioning-and-publication.md#commit-classification)
  requires breaking classification to take precedence and the highest required
  increment across the release range to win. During `0.x`, both a compatible
  feature and an incompatible change require a minor release through the
  candidate promotion flow.

### Trigger and observed code path

1. Establish candidate and stable history through `0.1.0`.
2. Create a branch containing an ordinary `fix: correct behaviour` commit.
3. Merge it into `main` using an ancestry-preserving merge whose message supplies
   feature or breaking classification. The holistic review reproduced each of
   these variants separately:

   | Merge message | Required release path | Observed plan |
   | --- | --- | --- |
   | `fix!: remove old API` with `BREAKING CHANGE: migrate calls` | Minor through RC promotion | Stable `0.1.1` |
   | `fix!: remove old API` without a footer | Minor through RC promotion | Stable `0.1.1` |
   | `fix: remove old API` with `BREAKING CHANGE: migrate calls` | Minor through RC promotion | Stable `0.1.1` |
   | `feat: introduce new API` | Minor through RC promotion | Stable `0.1.1` |

4. The planner reads commit messages with `parse_message()`, which sees the
   qualifying merge message and allows version calculation to proceed.
5. Semantic Release calculates the version with its default
   `ignore_merge_commits=True`, because the project does not override that
   option. It ignores the merge message and sees only the ordinary fix.
6. `plan("main")` returns tag `v0.1.1`, version `0.1.1`, and
   `prerelease=False`. The patch exemption skips candidate validation.
7. `prepare()` succeeds for that patch. In all four histories, its generated
   `0.1.1` notes include the ordinary fix but omit the feature or breaking merge
   description and any migration footer carried by that merge.
8. With an existing `1.0.0` stable tag, the same ordinary fix merged with
   `fix!: incompatible contract` plans and prepares `1.0.1`, rather than
   requiring major candidate promotion.

### Impact

The defect affects compatible features as well as breaking changes when their
classification is carried by a merge message. Version calculation falls back
to the constituent commits; when their highest increment is a fix, the merge
can be published as a stable patch without the required candidate promotion.
The generated notes also omit the merge's feature or migration information,
obscuring the change from consumers.

These are consequences of one parser-policy mismatch, not separate bugs. The
planner, version engine and note generator disagree about which commits
participate in release policy. Both release branches share this configuration;
the incorrect stable-patch outcomes above were reproduced on `main`.
The existing 21 focused release and artifact tests passed despite the defect.

### Suggested resolution

Align commit classification in the planner and release engine so qualifying
merge messages, including `feat`, breaking markers and breaking footers,
participate consistently in version selection and generated release notes.
Preserve neutral promotion and synchronization messages without introducing
duplicate release bumps.

### Validation expectation

Add isolated-history regression tests for an ordinary fix merged after `0.1.0`
with each qualifying merge message: `feat`, `!` without a footer, a breaking
footer without `!`, and both breaking forms together. Verify that none can
return or prepare stable `0.1.1` and that each requires the minor candidate
promotion path. Exercise the corresponding candidate calculations on
`release/next` and verify that prepared notes retain feature descriptions and
supplied migration guidance. Check note content, not just file existence.

Retain neutral promotion and synchronization coverage, and verify breaking
merge classification requires a major release once the stable line is `1.x`.
Planning, preparation and release notes must use the same classification policy.

### BUG-004: Initial release notes omit the delivered behaviour

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Pre-fix evidence:** reproduced with isolated Git histories during review on
  2026-10-05, including initial candidate preparation and stable promotion.
  Reconfirmed in the latest holistic review. No package was published.
- **Priority:** P2 — the initial release notes do not satisfy the agreed design.
- **Location:** [pyproject.toml](pyproject.toml), lines 116–117 (default changelog
  template configuration), and [scripts/release.py](scripts/release.py),
  `prepare()` changelog generation and retention.
- **Design requirement:** [First Candidate And Stable Release](docs/epics/05-releases/01-semantic-versioning-and-publication.md#first-candidate-and-stable-release)
  requires initial notes to describe reviewed delivered behaviour without
  inventing a previous release tag.

### Trigger and observed code path

1. Start with no release tags and explicit feature and fix commits, such as
   `feat: implement SQL workflows` and `fix: preserve session ownership`.
2. Plan and prepare the first candidate, `0.1.0rc1`.
3. Semantic Release uses its default `mask_initial_release=True`; the project
   neither overrides that setting nor supplies an initial release summary.
4. The retained `CHANGELOG.md` contains only the candidate heading and
   `Initial Release`, omitting both delivered changes.
5. In a separate promotion history, preparing the first stable release adds an
   empty `0.1.0` section above the masked candidate entry. Stable promotion
   therefore does not recover the missing initial behaviour descriptions.

The installed Semantic Release 10.7.0 behaviour matches its
[documented masking default](https://python-semantic-release.readthedocs.io/en/stable/configuration/configuration.html#mask-initial-release).
The existing preparation test asserts only that `CHANGELOG.md` exists, so it
passes despite the missing content.

### Impact

The automatically retained and published initial notes do not explain what
Quackframe delivers. Candidate reviewers and first stable consumers receive a
generic placeholder instead of the initial release description required by the
scope.

### Suggested resolution

Disable initial-release masking or provide an explicit reviewed initial summary.
Ensure the retained notes preserve the delivered behaviour through the first
stable promotion without inventing a previous release.

### Validation expectation

Add isolated-history tests that prepare an initial candidate containing known
feature and fix descriptions and assert the retained note content. Promote the
candidate and verify that the stable release notes still explain the delivered
behaviour. Check content and version identity, rather than file existence alone,
and retain coverage for subsequent candidate and stable release notes.

### BUG-005: An unpublished RC can authorize stable promotion

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Pre-fix evidence:** reproduced in the latest holistic review on 2026-10-05 with
  an isolated Git history and the staged workflow's Bash draft guard using a
  mocked GitHub CLI response. No hosted workflow or publication was performed.
- **Priority:** P2 — stable promotion can bypass the published-candidate gate.
- **Location:** [scripts/release.py](scripts/release.py), lines 131–142
  (candidate selection), and [.github/workflows/release.yml](.github/workflows/release.yml),
  lines 71–80 (draft and retained-artifact checks).
- **Design requirement:** [Stable Promotion](docs/epics/05-releases/01-semantic-versioning-and-publication.md#stable-promotion)
  and the [release guide](docs/releases.md#branches-and-versions) require
  promotion of the published, accepted RC. A reserved tag does not establish
  that the candidate is available for consuming-project acceptance.

### Trigger and observed code path

1. Create a qualifying candidate and its `v0.1.0-rc.1` tag.
2. Model failure after remote tag creation but before draft creation: the tag
   exists, but there is no GitHub draft or PyPI candidate publication.
3. Merge that candidate into `main`, preserving ancestry and its exact tree.
4. `plan("main")` accepts the tag and returns stable `0.1.0` without checking
   candidate publication state.
5. The workflow's draft guard exits successfully when the mocked draft list is
   empty. Its retained-artifact check concerns the new stable tag, not the RC.
6. No subsequent step checks publication of the RC used to authorize promotion.

As a control, the same guard rejects promotion when the response contains the
incomplete `v0.1.0-rc.1` draft. The missing case is a tag without a draft.

### Impact and suggested resolution

Stable publication is eligible even though the RC could not have been installed
from PyPI for acceptance. Verify completed publication and source/artifact
identity for the selected promotion candidate before authorizing the stable
release. Keep local version planning usable without publication credentials;
the workflow can enforce the remote publication prerequisite.

This does not reopen BUG-001. A later qualifying change may still allocate and
publish a newer version after an orphaned tag. The additional prerequisite
applies when relying on that specific candidate to authorize stable promotion;
it must not become a global requirement to repair all earlier publications.

### Validation expectation

Exercise the planner and workflow together for the selected RC with: a tag only;
an incomplete draft; completed matching publication; and conflicting source or
artifact evidence. Reject incomplete or conflicting promotion evidence and
accept completed matching evidence. Separately retain a test proving that a
newer qualifying candidate can publish after an earlier orphaned tag when no
incomplete draft blocks it.

### BUG-006: Patch-sized promotions bypass candidate-tree validation

- **Status:** Resolved locally on 2026-10-05 with persistent regression coverage.
- **Pre-fix evidence:** planning and preparation both reproduced in an isolated Git
  history during the latest holistic review on 2026-10-05. No package was
  published.
- **Priority:** P2 — a candidate promotion can include changes absent from its RC.
- **Location:** [scripts/release.py](scripts/release.py), lines 123–142,
  especially the `if not is_patch` exemption.
- **Design requirement:** The [promotion rule](docs/releases.md#branches-and-versions)
  requires the promoted tree to match the published RC exactly, explicitly
  including documentation changes. The [direct stable patch path](docs/epics/05-releases/01-semantic-versioning-and-publication.md#stable-patches)
  is a separate flow that does not require a candidate.

### Trigger and observed code path

1. Establish candidate and stable history through `0.1.0`.
2. Synchronize `main` into `release/next`, add a `fix` commit, and tag the
   calculated candidate `v0.1.1-rc.1`.
3. Add a documentation commit on `release/next` without publishing a fresh RC.
4. Promote `release/next` into `main` with a neutral, ancestry-preserving merge.
5. `plan("main")` classifies the target as a patch and skips all candidate
   selection and tree validation. It returns stable `0.1.1`.
6. `prepare()` succeeds and records `0.1.1` for the changed source, even though
   the RC and promotion tree hashes differ.

### Impact and suggested resolution

The patch-number exemption conflates direct stable fixes with RC promotions.
Preserve automatic direct patches while enforcing candidate freshness for a
promotion, regardless of the size of its version increment. This is independent
of BUG-003: the reproduced history uses ordinary `fix` and `docs` commits and a
neutral merge message, so correcting merge-message parsing alone does not fix it.

### Validation expectation

Pair a valid direct stable patch with patch-candidate promotions whose trees
match or differ. The direct patch and matching promotion must succeed; changed
promotion trees must fail until a fresh candidate is published. Cover both
documentation and code changes, and assert preparation cannot proceed after
failed promotion validation.

## Review Coverage And Fix Acceptance

The pre-fix review confirmed five open findings: BUG-002 through BUG-006.
BUG-001 remains closed. The staged implementation was assessed against both the
scope and its unstaged recovery clarification. The scope's statement that local
implementation is complete is not evidence that these unresolved requirements
have been met.

To reduce repeated discoveries, use the following acceptance process for the
release fixes. This defines required validation; it does not claim
that the current test suite covers every row or that any review proves zero bugs.

1. Map each release rule in the scope to a concrete initial state, trigger,
   expected version, allowed side effects, and failure outcome before changing
   the implementation. Use the table below as the starting set; account for
   interactions between rules, not only each rule in isolation.
2. Turn every open bug into a failing regression test first. Keep those tests
   in the repository and verify that each fails for the documented reason on
   the current implementation.
3. Exercise the complete decision path: classification, planning, preparation,
   workflow eligibility, retained artifacts, upload reconciliation and
   finalization. A helper test passing does not prove the workflow enforces it.
4. Assert release-note content, source identity, distribution metadata and
   publication eligibility, rather than only version numbers or file existence.
5. After implementing the fixes together, review one fixed revision against
   this coverage map. Record uncovered scenarios and hosted-only checks as
   unverified; do not describe passing local checks as production readiness.

| Scenario family | Required cases and outcomes |
| --- | --- |
| Bootstrap | Feature-only, fix-only and breaking history reach `0.1.0rc1`, later RCs, then `0.1.0`; maintenance alone does not release. |
| Classification | Ordinary commits and qualifying merge messages; `feat`, `fix`, `perf`, `!`, footer-only breaking changes and mixed ranges; correct highest bump during both `0.x` and `1.x`; neutral promotion/sync does not add a bump. |
| Promotion | Minor, major and patch RCs; matching and changed trees; tag-only, draft, completed and conflicting publication evidence. |
| Direct patches | Compatible fixes on `main` remain automatic without an RC; feature/breaking changes cannot use the exemption. |
| Parallel branches | Stable patch alongside the next candidate; stale ancestry rejection; synchronization alone produces no RC; refreshed candidate preserves the intended target. |
| Notes and metadata | Initial and subsequent RC/stable notes retain delivered behaviour and migration text; package version, tag, source and retained evidence agree. |
| Recovery | Failure before a tag, after a tag but before a draft, during asset retention, during partial upload and before finalization; completed retry is a no-op; conflicting identity fails. |
| Recovery interaction | Orphaned history permits a newer qualifying release; incomplete drafts block it; an unpublished selected RC cannot authorize promotion. |
| Workflow eligibility | Successful trusted push on an allowed branch; failed CI, PR runs, other branches, superseded source and duplicate triggers; serialized candidate/stable publication. |
| Distribution | Build the wheel from the sdist; inspect metadata and hashes; install the exact wheel in a clean Poetry consumer; exercise CLI/Python ordering, shared session and fail-fast behaviour without Prefect. |

### Latest review evidence, 2026-10-05

- All 21 focused release/artifact tests passed despite the five findings.
- Additional isolated histories exercised the cases described above. The actual
  staged Bash draft guard was run with mocked GitHub responses for BUG-005.
  This verifies local control flow, not GitHub's hosted permissions or API state.
- An exact-index package copy built its sdist and wheel, passed Twine and
  metadata/checksum validation, and passed clean Poetry-consumer Python/CLI
  smoke tests without Prefect.
- Fourteen artifact checks covered absent, partial and complete uploads,
  conflicting or unexpected files, corruption of each retained evidence/file
  type, HTTP errors and successful PyPI hash-response parsing.
- Lock validation, scoped Ruff lint/formatting, Pyright, documentation links
  and diff checks passed. Repository-wide Ruff reported 13 findings in the
  unchanged prototype.
- Full pytest finished with 416 passed, three expected failures and one failure
  in `test_layer_diagnostics[traced-4-fsspec]`: the unprotected upstream SFTP
  control raised `Garbage packet received`. Its isolated rerun produced the
  expected deadlock-related xfail. The full-suite result was not clean; the
  failure was not attributed to the staged release changes.
- Actionlint passed after excluding its obsolete schemas for `concurrency.queue`
  and the App action's `client-id` input, which were checked against current
  official documentation and action metadata.
- Hosted GitHub permissions, branch protections, PyPI/OIDC and actual
  publication remain unverified. No package was published during review.

Disposable local evidence is under `.release-test-tmp-audit-01/`, including
`results.json`, `extra-results.json`, `patch-promotion-evidence.json` and
`artifact-results.json`. These ignored files supplement the reproductions
recorded here; durable regression tests must not depend on their presence.

## Reclassified Findings

### BUG-001: An orphaned release tag does not block later publication

- **Status:** Closed on 2026-10-05; intended behaviour, not an implementation bug.
- **Decision:** The [publication and recovery scope](docs/epics/05-releases/01-semantic-versioning-and-publication.md#publication-and-recovery)
  explicitly permits a later qualifying change to publish a newer version when
  an earlier tag was created but GitHub draft creation failed before a draft
  existed. The tag reserves its version and remains release history even if
  publication never completes. This follows the inspected MAD.Prefect and WebUI
  strategies; a newer release does not automatically repair the earlier one.
- **Reason for reclassification:** The original finding incorrectly applied
  same-version retry safeguards to every later release. Requiring all earlier
  tags to have completed publication would add a recovery restriction outside
  the agreed scope. The proposed global block and its regression expectation
  are withdrawn; no implementation fix is required for this finding.
- **Recovery boundary:** Retrying the earlier version still requires verified
  source and artifact identity. Quackframe's separate incomplete-draft guard
  remains in place, as described in the [release guide](docs/releases.md#validation-and-recovery).
