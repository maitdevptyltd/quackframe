# Versioning And Releases

Quackframe uses Poetry for dependency management, Hatchling for distribution
builds, and Python Semantic Release for Conventional Commit analysis and release
notes. GitHub Actions publishes validated packages to PyPI. Release tooling is
development-only and does not add runtime dependencies to the installed wheel.

## Branches And Versions

| Change | PR target | Publication after successful CI |
| --- | --- | --- |
| Upcoming feature or candidate correction | `release/next` | RC, initially `0.1.0rc1` |
| Accepted candidate promotion | `main` | Stable, initially `0.1.0` |
| Compatible fix to an existing stable version | `main` | Next patch, for example `0.1.1` |
| Documentation or internal maintenance only | Either | No new release |

Candidates are automatic; there is no separate manual release request. Before
the first stable release, corrections belong on `release/next`, since there is
no stable package to patch. Ordinary `main` pushes without an RC to promote
return no release. Explicit promotion requests still require a valid candidate.
Promote candidates with an ancestry-preserving merge
from `release/next` to `main`, not a squash. Use a neutral promotion message such
as `chore(release): promote Quackframe 0.1.0`.

The workflow uses the latest reachable RC for the calculated stable version.
The promotion PR records consuming-project acceptance in normal prose; there are
no machine-parsed `Candidate:` or `Acceptance:` fields. The merged PR's source
branch distinguishes promotion from a direct stable fix. Missing or ambiguous
merge provenance stops publication. An older RC cannot be selected through PR
text: if the latest RC does not match, validate and publish a fresh candidate.
The selected RC needs a completed GitHub prerelease, matching source/version
records, and both matching distributions on PyPI. A tag alone, draft, partial
upload or evidence-read error cannot authorize promotion.

The promotion tree must match the published RC's source tree exactly. Review
the candidate's scope, migration notes and a consuming-project smoke test before
merging. If either line changes, synchronize and validate a fresh candidate
before promotion. Even documentation changes after an RC change its tree; include
them in a subsequent qualifying candidate rather than promoting untested source.

After stable publication, synchronize `main` back into `release/next`. Do the
same after a direct stable patch. Synchronization alone does not publish another
RC. A stable fix can coexist with the next minor candidate: `0.1.1` does not
change the upcoming `0.2.0rcN` target. Candidate testing must include that fix.
If a direct patch consumes a patch candidate's target version, synchronize and
cut a fresh candidate for the next version. Merging the stale candidate does
not let its changes ship through a later direct patch: uncovered RC ancestry
still requires a valid promotion.

Git tags use the release engine's SemVer form, such as `v0.1.0-rc.1`. Python
package metadata uses the equivalent PEP 440 form `0.1.0rc1`. Stable tags are
`v0.1.0`. Install an exact candidate in a consuming Poetry project with:

```powershell
poetry add "quackframe==0.1.0rc1"
```

## Change Classification And Compatibility

`feat` requests a minor release; `fix` and `perf` request a patch. A `!` or
`BREAKING CHANGE` footer takes precedence. During `0.x`, a breaking change
requests a minor release with migration notes. From `1.0` onward it requests
a major release. Moving to `1.0` is an explicit future policy change, not a
side effect of an initial breaking commit.

Unmarked `docs`, `test`, `refactor`, `build`, `ci`, and `chore` commits do not
request releases. Classify an installation/runtime correction as `fix`, even
when it changes only dependencies or packaging. Keep the final commit message
and breaking footer when squash-merging a short-lived feature or fix PR.
The release tool does not scan a squash message's embedded commit list.
Qualifying ancestry-preserving merge messages participate in classification and
release notes, including breaking markers and footers carried only by the merge.

Compatibility covers documented Python imports, signatures, models and results;
SQL functions; CLI options and exit behaviour; configuration keys and precedence;
optional adapter/provider contracts; and ordering, shared-session, cleanup and
failure semantics. Removing supported Python or integration versions is also a
compatibility change. Private helpers are not public solely because they are
importable. Pre-release development maintains one current API without shims;
published changes still need accurate notes and version classification.

## Publication Identity

The Release workflow follows successful **push** runs of CI on the two supported
branches. PR CI, other branches, failed CI and superseded branch commits cannot
publish. The repository variable `QUACKFRAME_RELEASES_ENABLED` must be `true`.

The workflow calculates the version from Git history and stamps
`[project].version` in its isolated build checkout. It does not commit or push
generated metadata back to protected branches. Source metadata therefore remains
a development baseline; tags and published distribution metadata identify actual
releases. `poetry run python -m build --no-isolation` invokes Hatchling, building
the wheel from the source distribution to check both packaging paths.

The source distribution contains the package source, README, licence and project
metadata (plus Hatchling's build metadata and `.gitignore`). Tests, release scripts, development
documentation and the Poetry lock remain in the repository, not the package.

The workflow has four jobs: plan, package, publish, and finalize. Packaging builds
one wheel and one source distribution, checks their metadata, and smoke-tests
installation, Python/CLI execution, shared state and fail-fast behaviour in a
clean Poetry consumer without Prefect. Its immutable `release-bundle` workflow
artifact contains those files, generated `CHANGELOG.md` and a small `release.json`
source/version/flow record. GitHub keeps this artifact for 90 days. There is no
sealed hash manifest, pre-upload tag reservation or retained draft release.

The publish job compares distribution metadata and the source/version record
against the planner's independent job output, computes hashes from the original
build, and uploads only missing files through PyPI Trusted Publishing. Existing
files must have identical hashes. After bounded visibility polling verifies both
files, finalization creates the tag at the tested source commit and the GitHub
release with the original bundle attached. RCs are marked prereleases and do not
replace the latest stable release. Notes describe delivery since the preceding
stable release, including candidate work and supplied migration guidance.

All tooling, locked dependencies and version policy come from the workflow's
immutable default-branch commit (`github.sha`). Candidate files supply only Git
history and build source. Python isolated mode and the trusted entrypoint exclude
candidate modules, `PYTHONPATH` and user site packages. Land tooling changes on
`main` before relying on them for a candidate.

The plan job has read-only contents and PR access. Candidate builds and smoke
tests run separately with read-only repository permission, no protected
environment, App key or OIDC rights. Only publish has OIDC permission. Publish
and finalize consume the planner's decision through job outputs and inspect
packages as data; they never execute the wheel. Finalize alone uses a short-lived
GitHub App token with contents/workflows write permission, because candidates
may change workflow files. The token is scoped to this repository, exposed only
to finalization, and revoked at job end. Checkout never persists credentials.
App-token and PyPI actions remain pinned to verified commit SHAs.

Both branches share one non-cancelling publication queue. Timeouts are 15 minutes
for planning, 30 for packaging, 15 for publication and 10 for finalization.

## Repository Owner Setup

Implementation alone does not configure external services or publish a package.
Before the first candidate merge:

1. Land the release infrastructure on the default branch so GitHub can discover
   its `workflow_run` trigger. Keep publication disabled during setup.
2. Verify remote tags and PyPI history. The first candidate must be `0.1.0rc1`
   and the first stable version `0.1.0`; stop if those identities conflict.
3. Establish `release/next` from the appropriate reviewed `main` base. Protect
   both branches with required CI and review; prevent direct unreviewed pushes.
   Permit ancestry-preserving promotion merges.
4. Create the GitHub environment `pypi`. Set **Deployment branches and tags** to
   **Selected branches and tags**, with one **branch** rule: `main`. Do not allow
   tags, `release/next`, wildcard branches or all protected branches. An environment
   does not restrict access by workflow filename. Configure a PyPI pending Trusted
   Publisher if the project does not
   exist: owner `maitdevptyltd`, repository `quackframe`, workflow `release.yml`,
   environment `pypi`. Confirm maintainers and account access.
5. Create and install a GitHub App on this repository with repository **Contents:
   Read and write** and **Workflows: Read and write** permissions. Store its client
   ID in the repository variable `QUACKFRAME_RELEASE_APP_CLIENT_ID` and its private
   key as `QUACKFRAME_RELEASE_APP_PRIVATE_KEY` in the `pypi` **environment secrets**,
   never as a repository or broadly available organization secret. The workflow
   uses `actions/create-github-app-token` to mint a token for the current repository
   in each release-writing job. The App needs no branch-protection bypass.
   If a repository secret already exists, an owner must set the environment secret
   from their secure original key; GitHub cannot return its existing value. Confirm
   the replacement's name and environment scope before removing the repository
   copy. Do not enable releases while the broadly scoped copy remains available.
6. Verify `main` is the default branch and confirm environment/ref behaviour and
   token permissions in GitHub. `workflow_run` executes in the default-branch
   context, so `main`-only environment rules also permit RC publication. The
   workflow independently requires `refs/heads/main` and uses its immutable SHA
   for tooling; the triggering CI SHA identifies only the build source.
   Finalization uses `pypi` so its App key receives the same restriction. Rehearse
   partial-upload and finalization retries using the original workflow artifact,
   including a candidate containing workflow changes.
7. Set `QUACKFRAME_RELEASES_ENABLED=true` only when ready for qualifying merges
   to publish. Do not add a routine manual RC/patch approval gate that contradicts
   the agreed automatic flow.

As checked on 2026-10-02, the remote had no release tags or `release/next` branch,
and the PyPI package endpoint returned 404. This is not a reservation of the name.
Recheck before activation. Forks must configure their own identity and workflow.

## Validation And Recovery

`poetry run python -m scripts.release release/next` previews a release on that
branch. Without `--prepare`, it changes no files. Use an isolated checkout for
`--prepare`; it stamps metadata and notes without committing, tagging or
publishing. Local plans remain proposals until the workflow checks provenance.

Use **Re-run failed jobs** on the original Release run after correcting a
transient failure. Successful package jobs are not rerun, so publication and
finalization download the same `release-bundle`. **Re-run all jobs** is rejected
with instructions; it must not rebuild a version whose upload may have begun.
A superseded source also fails explicitly during planning. If planning failed,
rerun CI for the current commit to start a fresh release run. Maintenance-only
changes and disabled publication are intentional no-release outcomes.

| Failure | Action |
| --- | --- |
| Before upload | No release tag or draft has been reserved. Rerun failed jobs; a failed package job can build again because publish has not run. |
| Partial upload or visibility timeout | Rerun failed jobs on the original run. The original bundle is compared with PyPI; only missing identical-build files are uploaded. Conflicts stop immediately and never overwrite files or choose another version. |
| PyPI complete, GitHub finalization failed | Rerun failed jobs. Finalization rechecks PyPI hashes and uses the original bundle. A matching existing tag is accepted; a conflicting tag fails. An already complete matching GitHub release is a no-op. |
| GitHub CLI left an incomplete draft during finalization | A maintainer inspects that release, removes only the incomplete draft while preserving its matching tag, then reruns failed jobs. Unrelated drafts never block publication. |
| Original workflow artifact expired or was deleted | Automatic recovery ends. Recover the original bundle from a trusted copy and compare its identity and PyPI hashes before maintainer-reviewed completion. Do not rebuild and assume byte identity, move tags, overwrite PyPI files, or rerun all jobs. If original bytes cannot be recovered, stop and resolve the interrupted version explicitly before proceeding. |

Complete an interrupted publication before merging further release work. There
is no global draft lock or automatic search across earlier runs. A later run
does not repair an earlier upload. A defective published package requires a
corrected version; yanking is a separate maintainer action.

Verification polls missing PyPI files every 20 seconds for up to three minutes;
an in-flight request may take another 30 seconds. Hash conflicts and unrelated
errors fail immediately. No upload is retried by this polling loop.

Hosted acceptance remains pending: the local synthetic tests cannot establish
GitHub environment restrictions, queued reruns, App permissions, PyPI OIDC or
actual upload/finalization behaviour. Keep `QUACKFRAME_RELEASES_ENABLED` unset
or false until an owner completes the setup and authorised hosted rehearsal.

## Related Docs

- [Contributing](../CONTRIBUTING.md): development and validation commands.
- [Release Implementation Scope](epics/05-releases/01-semantic-versioning-and-publication.md):
  accepted direction, implementation evidence and outstanding activation work.
- [Developer API](developer-api.md): public Python and CLI contracts.
- [Python Semantic Release](https://python-semantic-release.readthedocs.io/en/stable/):
  version analysis and multi-branch release engine.
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): publisher setup.
- [GitHub release permissions](https://docs.github.com/en/rest/releases/releases):
  release creation and workflow-write requirements.
- [GitHub App token action](https://github.com/actions/create-github-app-token):
  installation credentials, repository scope and token revocation.
