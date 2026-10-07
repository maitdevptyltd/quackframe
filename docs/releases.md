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
no stable package to patch. Promote candidates with an ancestry-preserving merge
from `release/next` to `main`, not a squash. Use a neutral promotion message such
as `chore(release): promote Quackframe 0.1.0`.

The promotion PR identifies the exact published candidate and records its
consuming-project acceptance with these two lines in its description:

```text
Candidate: v0.1.0-rc.1
Acceptance: Link to the consuming-project smoke result and reviewed limitations.
```

Use the actual candidate tag and acceptance evidence. The workflow reads the
merged PR associated with the validated source commit to distinguish promotions
from direct fixes. Missing or ambiguous provenance stops publication. A patch
candidate follows the same promotion checks as a minor or major candidate.
The selected RC needs a completed GitHub prerelease, matching retained source
and artifact evidence, and both matching distributions on PyPI. A tag alone,
a draft, a partial upload or an evidence-read error cannot authorize promotion.

The PR's explicit selection is read before candidate validation. An earlier
accepted RC can be promoted if its exact tree and ancestry match, even when a
newer RC has a different tree. The workflow does not replace your selection with
the newest candidate.

The promotion tree must match the published RC's source tree exactly. Review
the candidate's scope, migration notes and a consuming-project smoke test before
merging. If either line changes, synchronize and validate a fresh candidate
before promotion. Even documentation changes after an RC change its tree; include
them in a subsequent qualifying candidate rather than promoting untested source.

After stable publication, synchronize `main` back into `release/next`. Do the
same after a direct stable patch. Synchronization alone does not publish another
RC. A stable fix can coexist with the next minor candidate: `0.1.1` does not
change the upcoming `0.2.0rcN` target. Candidate testing must include that fix.

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

Each release retains its wheel, source distribution, generated `CHANGELOG.md`,
`release.json` source/version record, and `SHA256SUMS.json` in a draft GitHub
release before upload. The tag points at the tested source commit; the source
distribution includes the stamped version. The workflow tests installation,
Python and CLI execution, shared session state, and fail-fast behaviour in a
clean Poetry consumer without Prefect.

The saved decision records candidate, promotion or direct-patch flow and, for
promotions, the selected candidate tag and source. Preparation revalidates that
decision before generating notes and stamping metadata. Each release's notes
describe delivery since the preceding stable release, so initial and promoted
releases retain the feature, fix and migration descriptions from candidate work.

PyPI upload uses Trusted Publishing in the `pypi` environment. Only that job
receives OIDC permission. The workflow compares published file hashes with the
retained artifacts before making the GitHub release public. RCs are marked as
prereleases and cannot replace the latest stable GitHub release.

The package job uses `GITHUB_TOKEN` with `contents: write` because GitHub requires
push access to list and download draft releases during recovery. Retention and
finalization use short-lived GitHub App installation tokens with `contents: write`
and `workflows: write`: candidates may change workflow files relative to the
default branch, which `GITHUB_TOKEN` cannot authorize. Each token is scoped to
the current repository, exposed only to its release step, and revoked at job end.
The package job also needs `pull-requests: read` for merged-PR provenance.

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
4. Create the GitHub environment `pypi`, limited to the intended trusted release
   workflow. Configure a PyPI pending Trusted Publisher if the project does not
   exist: owner `maitdevptyltd`, repository `quackframe`, workflow `release.yml`,
   environment `pypi`. Confirm maintainers and account access.
5. Create and install a GitHub App on this repository with repository **Contents:
   Read and write** and **Workflows: Read and write** permissions. Store its client
   ID in the repository variable `QUACKFRAME_RELEASE_APP_CLIENT_ID` and its private
   key in the Actions secret `QUACKFRAME_RELEASE_APP_PRIVATE_KEY`. The workflow
   uses `actions/create-github-app-token` to mint a token for the current repository
   in each release-writing job. The App needs no branch-protection bypass.
6. Verify `workflow_run` environment/ref behaviour and token permissions in
   GitHub. This trigger runs in the default-branch context while the workflow
   explicitly validates and checks out the triggering source. Environment
   restrictions must account for that context. Rehearse recovery from a draft
   release and publication of a candidate containing workflow changes.
7. Set `QUACKFRAME_RELEASES_ENABLED=true` only when ready for qualifying merges
   to publish. Do not add a routine manual RC/patch approval gate that contradicts
   the agreed automatic flow.

As checked on 2026-10-02, the remote had no release tags or `release/next` branch,
and the PyPI package endpoint returned 404. This is not a reservation of the name.
Recheck before activation. Forks must configure their own identity and workflow.

## Validation And Recovery

`poetry run python -m scripts.release release/next` previews a release when the
checkout is on that branch. Without `--prepare`, it changes no files. Use an
isolated checkout for `--prepare`, which stamps metadata and generates notes but
does not commit, tag, push or publish. Local builds are not production releases.
Local plans are proposals; the workflow still verifies merged-PR provenance and
remote publication evidence. A reserved release cannot be prepared again: use
its original retained bundle instead.

Rerun the failed GitHub Release workflow after fixing transient access problems.
Before a tag exists, the run can rebuild. Once a tag exists, retries download the
original retained assets and verify source identity and checksums; they do not
rebuild. Existing PyPI files must match, and only missing files are uploaded.
An already complete upload becomes a no-op before GitHub release finalization.

Recovery finds both drafts and published releases through GitHub's paginated
release listing with push access. A 404 from the published-release-by-tag
endpoint does not establish that a retained draft is missing. Promotion still
requires a published candidate; finding its draft does not authorize promotion.

A remote tag reserves its version even if publication fails. If draft creation
fails before a draft exists, a later qualifying merge may publish a newer version.
The earlier tag remains part of release history, and that version may remain
unpublished. A newer publication does not repair or reuse the earlier version.
An incomplete GitHub draft still blocks later publications until recovery.

To recover a tagged version whose draft or assets are missing, do not delete or
move the tag to force a retry. Recover the exact artifacts from the original
workflow's retained `release-bundle`, reconcile them with the original source
and hashes, and restore missing draft assets through a maintainer-reviewed
recovery. If identity cannot be proved, stop that recovery and investigate.
Conflicting PyPI files for the version being uploaded stop its publication.
A defective published package needs a corrected version; yanking is a separate
maintainer action.

Both release lines share one non-cancelling concurrency group with `queue: max`,
so pending stable and candidate runs do not replace each other. GitHub's
[concurrency queue](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
holds up to 100 waiting runs; investigate and rerun any rejected overflow.
Superseded runs skip publication until their branch's newest source passes CI.
To retain automatic retry of the failed version, keep its branch at the original
source until recovery is complete: automatic retries reject superseded source.
If the branch advances, preserve the original source/artifacts for manual
recovery. Advancing to a newer release remains subject to the draft guard above.

## Related Docs

- [Contributing](../CONTRIBUTING.md): development and validation commands.
- [Release Implementation Scope](epics/05-releases/01-semantic-versioning-and-publication.md):
  accepted direction, implementation evidence and outstanding activation work.
- [Developer API](developer-api.md): public Python and CLI contracts.
- [Python Semantic Release](https://python-semantic-release.readthedocs.io/en/stable/):
  version analysis and multi-branch release engine.
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): publisher setup.
- [GitHub release permissions](https://docs.github.com/en/rest/releases/releases):
  draft visibility and workflow-write requirements.
- [GitHub App token action](https://github.com/actions/create-github-app-token):
  installation credentials, repository scope and token revocation.
