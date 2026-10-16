# Semantic Versioning And Package Publication

Status: **In Progress**
Last updated: 2026-10-16
Epic: 05 Releases
Phase: 01
Related docs: [Release Guide](../../releases.md), [Roadmap](../../roadmap.md), [Developer API](../../developer-api.md), [Contributing](../../../CONTRIBUTING.md)

## Outcome And Scope

Publish automatic RCs from `release/next`, stable promotions through reviewed
ancestry-preserving merges to `main`, and compatible stable fixes directly from
`main`. Keep Poetry for environments, Hatchling for packaging and Python Semantic
Release for Conventional Commit classification, versions and release notes.
The first candidate is `0.1.0rc1`, subsequent qualifying candidates increment its
RC number, and first stable promotion is `0.1.0`.

On 2026-10-16, S04 authorised removal of the pre-publication reservation and
retained-draft recovery system. The implemented sequence is plan, build, publish,
then tag/release. It preserves publication integrity without an automatic
cross-run recovery framework. Operator steps and failure handling live in the
[release guide](../../releases.md#validation-and-recovery).

Out of scope: runtime behaviour, customer deployment, extra prerelease channels,
multiple maintenance lines, environment administration and live publication.
The phase stays **In Progress** until hosted acceptance and activation complete.

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

## Release Decisions

The workflow verifies successful push CI for the exact current source on one
of the two release branches, repository identity, and one merged PR. It derives
promotion versus patch from merged-PR provenance before calculating the version.
Ordinary main pushes before the first stable release return no release; explicit
promotion still requires a valid published candidate.

Promotion selects the latest reachable RC targeting the calculated stable
version. Its source tree must exactly match the promotion before version
stamping, including docs, configuration and workflows. Its GitHub prerelease
must be complete, its tag must identify the expected source, and both PyPI
files must match the attached distributions. The latest stable release must be
in ancestry. Uncovered RC ancestry cannot fall through as a direct stable patch,
even when an intervening stable patch consumed the old RC's version.

There is no PR-body selection protocol. Consuming-project acceptance remains
part of normal promotion review. If the latest RC tree does not match, cut and
validate a new candidate rather than selecting an older RC through PR text.
The internal planner can still accept an explicit candidate when revalidating
the already calculated release decision during package preparation.

Maintenance and synchronization-only changes do not release. Qualifying commit
classification, bootstrap, neutral promotion messages and parallel stable patch
lineage retain the existing real-Git-history regression coverage.

## Workflow And Trust

1. **Plan:** default-branch tooling and locked dependencies inspect candidate
   history under read-only contents/PR permissions. The output records source,
   branch, tag, package version, flow and selected RC identity.
2. **Package:** a separate read-only runner checks out that exact source,
   revalidates the decision, stamps metadata, builds an sdist and wheel, checks
   metadata/Twine and runs the installed-wheel smoke test. It uploads one
   immutable workflow artifact retained for 90 days.
3. **Publish:** trusted code compares the artifact with the independent planner
   output and validates package metadata. It hashes the original distributions,
   stages only files absent from PyPI, uploads through Trusted Publishing, and
   verifies hashes with bounded polling. Conflicting bytes fail immediately.
4. **Finalize:** trusted code rechecks publication, then creates the tag and
   public GitHub release with the original bundle attached. Matching completed
   releases are no-ops; matching tag-only states can finish creation.

All executable tooling and policy come from immutable `github.sha` on the default
branch. Candidate code runs only during packaging, without the protected
`pypi` environment, App credentials or OIDC. Python isolated mode prevents
candidate import-path injection. Privileged jobs inspect distributions as data.
Publish alone has OIDC permission; finalize alone receives the repository-scoped
short-lived App token. Token-consuming steps, pinned privileged actions,
credential-free checkout and bounded job timeouts remain enforced.

Both release lines share the same non-cancelling queue. The gate remains disabled
unless `QUACKFRAME_RELEASES_ENABLED=true`. No environment or repository settings
are changed by this implementation.

## Failure Contract

Before upload there is no reserved tag or retained draft. Failure therefore
requires no reservation repair. After upload begins, **Re-run failed jobs**
reuses the successful package job's original artifact. Existing PyPI hashes must
match; only missing files are staged. No replacement version is allocated by a
retry. Bounded verification tolerates cached missing files without retrying an
upload. Finalization can be retried independently after PyPI is verified.

**Re-run all jobs** fails explicitly to prevent rebuilding an interrupted
publication; superseded CI source also fails rather than silently succeeding.
A failed planning job can be replaced by rerunning CI for the current source.
This intentionally distinguishes a fresh release attempt from continuing failed
publication jobs with an existing build.

No global draft lock, pre-upload tag reservation, sealed checksum manifest,
retained-draft downloader or automatic cross-run recovery remains. A CLI-created
incomplete draft can require maintainer removal of that draft only before
retrying finalization; unrelated drafts are ignored. The workflow artifact and
small source/version record are retained because they identify the original
build and keep retries and promotion verification straightforward.

If the artifact is gone, automatic retry is unavailable. A maintainer must
recover the original bytes and verify identity/hashes before completion; a
rebuild is not evidence of byte equality. Complete interrupted publication before
new release work. See the guide's failure table for exact operator actions.

## Validation And Acceptance

Local regression files:

- [Release histories](../../../tests/test_release.py): bootstrap, commit/breaking
  classification, notes, preparation, stable ancestry, patch/minor promotion,
  exact trees, synchronization, version collision and no-release behaviour.
- [Workflow paths](../../../tests/test_release_workflow.py): eligibility,
  independent decision validation, trusted import paths, permissions and job
  order, missing/partial/complete upload states, finalization, tag conflicts,
  unrelated drafts and completed candidate proof without PR-body metadata.
- [Artifact checks](../../../tests/test_release_artifacts.py): distribution
  identity, exact file set, conflicting/missing PyPI files, bounded visibility
  polling and immediate failure on unrelated remote errors.
- [Package smoke](../../../scripts/package_smoke.py): clean Poetry consumer,
  Python/CLI execution, ordering, shared-session and fail-fast behaviour without
  optional orchestration dependencies.

S04 validation is offline with synthetic Git histories and controlled remotes.
The workflow test adapter invokes Python commands from YAML; it does not execute
hosted Actions, the actual publisher, or every line of multi-line build steps.
Earlier local package rehearsals remain historical evidence, not proof of this
workflow's hosted behaviour. Current check results are recorded with the S04
review resolution.

Before enabling publication, an owner must verify default-branch tooling,
protected-environment restrictions, App token scope, OIDC, queue/rerun semantics,
real package smoke and an authorised publication/finalization rehearsal,
including a candidate that changes workflow files. Remote package/tag history
must still confirm the bootstrap identities are available. No hosted acceptance
or live publication is claimed here.

## Related Docs

- [Release Guide](../../releases.md): branch policy, owner setup and failure actions.
- [Documentation Index](../../README.md): developer documentation map.
- [Roadmap](../../roadmap.md): delivery and activation status.
- [Contributing](../../../CONTRIBUTING.md): local validation and commit conventions.
