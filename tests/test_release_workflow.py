"""Run the workflow entrypoints with real Git histories and controlled remotes."""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scripts import release_artifacts as artifacts
from scripts import release_workflow as workflow
from scripts.release import git, plan
from scripts.release_identity import Release
from tests.test_release import change_file, commit, first_stable, tag_release
from tests.test_release import history as history

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"


def workflow_step(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute the actual Python command selected by the named workflow step."""
    block = (
        WORKFLOW.read_text(encoding="utf-8")
        .split(f"- name: {name}\n", 1)[1]
        .split("\n      - ", 1)[0]
    )
    match = re.search(r"^        run: (.+)$", block, re.M)
    assert match
    command_line = match[1]
    if command_line == "|":
        command_line = block.split("        run: |\n", 1)[1].splitlines()[0].strip()
    for name in ("SOURCE", "TAG"):
        command_line = command_line.replace(f"${name}", os.environ.get(name, ""))
    arguments = shlex.split(command_line)
    if arguments[:2] == ["poetry", "run"]:
        arguments = arguments[2:]
    assert arguments[:2] == ["python", "-m"]
    assert arguments[2] in {"scripts.release_workflow", "scripts.release_artifacts"}
    monkeypatch.setattr(sys, "argv", ["release_workflow", *arguments[3:]])
    if arguments[2] == "scripts.release_workflow":
        workflow.main()
    else:
        artifacts.main()


def make_bundle(release: Release, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    metadata = f"Name: quackframe\nVersion: {release.version}\n".encode()
    with zipfile.ZipFile(
        destination / f"quackframe-{release.version}.whl", "w"
    ) as wheel:
        wheel.writestr(f"quackframe-{release.version}.dist-info/METADATA", metadata)
    with tarfile.open(
        destination / f"quackframe-{release.version}.tar.gz", "w:gz"
    ) as sdist:
        entry = tarfile.TarInfo(f"quackframe-{release.version}/PKG-INFO")
        entry.size = len(metadata)
        sdist.addfile(entry, io.BytesIO(metadata))
    (destination / "release.json").write_text(
        json.dumps(asdict(release)), encoding="utf-8"
    )
    if not (destination / "CHANGELOG.md").exists():
        (destination / "CHANGELOG.md").write_text(
            f"# {release.tag}\nDelivered behaviour", encoding="utf-8"
        )
    artifacts.seal(destination)
    return destination


@dataclass
class Remote:
    root: Path
    tags: dict[str, str] = field(default_factory=lambda: {})
    releases: dict[str, dict[str, Any]] = field(default_factory=lambda: {})
    bundles: dict[str, Path] = field(default_factory=lambda: {})
    published: dict[str, dict[str, str]] = field(default_factory=lambda: {})
    prs: list[dict[str, Any]] = field(default_factory=lambda: [])
    writes: list[tuple[str, ...]] = field(default_factory=lambda: [])
    errors: set[str] = field(default_factory=lambda: set[str]())
    fail_create: bool = False

    def hashes(self, version: str) -> dict[str, str]:
        if "pypi" in self.errors:
            raise OSError("PyPI evidence unavailable")
        return self.published.get(version, {})

    def command(self, *args: str) -> str:
        assert args[0] == "gh", args
        if args[1:4] == ("api", "--method", "POST"):
            self.writes.append(args)
            self.tags[args[6].removeprefix("ref=refs/tags/")] = args[8].removeprefix(
                "sha="
            )
            return "{}"
        if args[1] == "api":
            endpoint = args[2]
            if any(error in endpoint for error in self.errors):
                raise subprocess.CalledProcessError(1, args, stderr="HTTP 503")
            if "/pulls?" in endpoint:
                return json.dumps([self.prs])
            if endpoint.endswith("/releases?per_page=100"):
                assert args[3:] == ("--paginate", "--slurp")
                # Separate pages keep recovery from relying on the first page.
                return json.dumps([[record] for record in self.releases.values()])
            tag = endpoint.split("/tags/")[-1]
            if "/git/ref/tags/" in endpoint and tag in self.tags:
                return json.dumps({"object": {"sha": self.tags[tag]}})
            # GitHub's by-tag endpoint only exposes published releases.
            # Drafts are visible in the authorized release listing above.
            if (
                "/releases/tags/" in endpoint
                and tag in self.releases
                and not self.releases[tag]["draft"]
            ):
                return json.dumps(self.releases[tag])
            if "/commits/" in endpoint and endpoint.rsplit("/", 1)[1] in self.tags:
                return json.dumps({"sha": self.tags[endpoint.rsplit("/", 1)[1]]})
            raise subprocess.CalledProcessError(
                1, args, stderr="gh: Not Found (HTTP 404)"
            )
        operation, tag = args[2:4]
        if operation == "download":
            if tag not in self.bundles:
                raise ValueError("Original retained assets are missing")
            shutil.copytree(self.bundles[tag], Path(args[5]), dirs_exist_ok=True)
        elif operation == "create":
            self.writes.append(args)
            if self.fail_create:
                raise OSError("Draft creation failed after tag reservation")
            destination = self.root / tag
            destination.mkdir()
            for filename in args[4 : args.index("--target")]:
                shutil.copy2(filename, destination)
            self.bundles[tag] = destination
            self.releases[tag] = {
                "tag_name": tag,
                "draft": True,
                "prerelease": "--prerelease" in args,
            }
        elif operation == "edit":
            self.writes.append(args)
            self.releases[tag]["draft"] = False
        else:
            raise AssertionError(args)
        return ""

    def candidate(self, release: Release, *, draft: bool = False) -> None:
        self.tags[release.tag] = release.source
        self.releases[release.tag] = {
            "tag_name": release.tag,
            "draft": draft,
            "prerelease": release.prerelease,
        }
        self.bundles[release.tag] = make_bundle(release, self.root / release.tag)
        self.published[release.version] = artifacts.verify(
            self.bundles[release.tag], release.source, release.tag
        )


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Remote:
    root = tmp_path / "remote"
    root.mkdir()
    value = Remote(root)
    monkeypatch.setattr(workflow, "command", value.command)
    monkeypatch.setattr(workflow, "published_hashes", value.hashes)
    monkeypatch.setattr(artifacts, "published_hashes", value.hashes)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/quackframe")
    monkeypatch.setenv("QUACKFRAME_RELEASES_ENABLED", "true")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    return value


def event_and_pr(
    remote: Remote,
    monkeypatch: pytest.MonkeyPatch,
    *,
    head: str = "release/next",
    candidate: str = "v0.1.0-rc.1",
) -> dict[str, Any]:
    branch, source = git("branch", "--show-current"), git("rev-parse", "HEAD")
    monkeypatch.setenv("SOURCE", source)
    run: dict[str, Any] = {
        "conclusion": "success",
        "event": "push",
        "head_branch": branch,
        "head_sha": source,
        "head_repository": {"full_name": "example/quackframe"},
    }
    Path("event.json").write_text(json.dumps({"workflow_run": run}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(Path("event.json").resolve()))
    remote.prs = [
        {
            "merged_at": "2026-10-05",
            "merge_commit_sha": source,
            "base": {"ref": branch, "repo": {"full_name": "example/quackframe"}},
            "head": {"ref": head, "repo": {"full_name": "example/quackframe"}},
            "body": (
                f"Candidate: {candidate}\n"
                "Acceptance: Consumer smoke passed for this exact candidate."
            ),
        }
    ]
    return run


@pytest.mark.parametrize(
    "state",
    [
        "tag-only",
        "draft",
        "partial",
        "complete",
        "source-conflict",
        "hash-conflict",
        "github-error",
        "pypi-error",
    ],
)
def test_tag_only_candidate_cannot_authorize_stable_publication(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    change_file("feature.txt", "feat: initial")
    candidate = plan("release/next")
    assert candidate
    git("tag", candidate.tag)
    remote.candidate(candidate)
    if state == "tag-only":
        remote.releases.clear()
        remote.bundles.clear()
        remote.published.clear()
    elif state == "draft":
        remote.releases[candidate.tag]["draft"] = True
    elif state == "partial":
        remote.published[candidate.version].pop(
            next(iter(remote.published[candidate.version]))
        )
    elif state == "source-conflict":
        remote.tags[candidate.tag] = "wrong-source"
    elif state == "hash-conflict":
        remote.published[candidate.version][
            next(iter(remote.published[candidate.version]))
        ] = "different"
    elif state == "github-error":
        remote.errors.add("/releases/tags/")
    elif state == "pypi-error":
        remote.errors.add("pypi")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    event_and_pr(remote, monkeypatch)
    workflow_step("Calculate or resume the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    assert decision.flow == "promotion"
    assert decision.candidate_source == candidate.source
    assert decision.version == "0.1.0"
    if state != "complete":
        with pytest.raises((ValueError, OSError)):
            workflow_step("Reuse retained artifacts on retry", monkeypatch)
        assert not Path("release-bundle").exists()
        assert not remote.writes
    else:
        workflow_step("Reuse retained artifacts on retry", monkeypatch)
        workflow_step("Stamp, build and check distributions", monkeypatch)
        assert "Initial" in Path("release-bundle/CHANGELOG.md").read_text()
        make_bundle(decision, Path("release-bundle"))
        workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
        assert len(remote.writes) == 2


@pytest.mark.parametrize("head", ["fix/example", "release/next"])
def test_patch_provenance_cannot_silently_fall_back(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    first_stable()
    change_file("fix.txt", "fix: stable correction")
    event_and_pr(remote, monkeypatch, head=head, candidate="v0.1.1-rc.1")
    if head == "release/next":
        with pytest.raises(ValueError, match="published RC"):
            workflow_step("Calculate or resume the release", monkeypatch)
    else:
        workflow_step("Calculate or resume the release", monkeypatch)
        decision = Release.read(Path("release-plan.json"))
        assert decision.flow == "patch"
        assert decision.version == "0.1.1"
        workflow_step("Reuse retained artifacts on retry", monkeypatch)
    assert not remote.writes


@pytest.mark.parametrize(
    "invalid",
    [
        "failed",
        "pr",
        "fork",
        "branch",
        "superseded",
        "disabled",
        "missing-pr",
        "ambiguous-pr",
        "missing-candidate",
        "missing-acceptance",
    ],
)
def test_workflow_eligibility(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    commit("feat: initial")
    tag_release("release/next", "0.1.0rc1")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    run = event_and_pr(remote, monkeypatch)
    if invalid == "failed":
        run["conclusion"] = "failure"
    elif invalid == "pr":
        run["event"] = "pull_request"
    elif invalid == "fork":
        run["head_repository"]["full_name"] = "other/fork"
    elif invalid == "branch":
        run["head_branch"] = "feature/example"
    elif invalid == "superseded":
        run["head_sha"] = "old-source"
    elif invalid == "disabled":
        monkeypatch.setenv("QUACKFRAME_RELEASES_ENABLED", "false")
    elif invalid == "missing-pr":
        remote.prs.clear()
    elif invalid == "ambiguous-pr":
        remote.prs *= 2
    elif invalid == "missing-candidate":
        remote.prs[0]["body"] = "Acceptance: passed"
    elif invalid == "missing-acceptance":
        remote.prs[0]["body"] = "Candidate: v0.1.0-rc.1"
    Path("event.json").write_text(json.dumps({"workflow_run": run}), encoding="utf-8")
    if invalid in {
        "missing-pr",
        "ambiguous-pr",
        "missing-candidate",
        "missing-acceptance",
    }:
        with pytest.raises(ValueError):
            workflow_step("Calculate or resume the release", monkeypatch)
    else:
        workflow_step("Calculate or resume the release", monkeypatch)
        assert "release=false" in Path("outputs").read_text()
    assert not Path("release-plan.json").exists()
    assert not remote.writes


@pytest.mark.parametrize("draft", [False, True])
def test_new_candidate_after_orphan_respects_draft_guard(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, draft: bool
) -> None:
    commit("feat: initial")
    old = tag_release("release/next", "0.1.0rc1")
    remote.tags[old] = git("rev-parse", "HEAD")
    if draft:
        remote.releases[old] = {"tag_name": old, "draft": True}
    change_file("correction.txt", "fix: newer correction")
    event_and_pr(remote, monkeypatch, head="fix/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    assert decision.version == "0.1.0rc2"
    if draft:
        with pytest.raises(ValueError, match="recovery"):
            workflow_step("Reuse retained artifacts on retry", monkeypatch)
        assert not remote.writes
    else:
        workflow_step("Reuse retained artifacts on retry", monkeypatch)
        workflow_step("Stamp, build and check distributions", monkeypatch)
        make_bundle(decision, Path("release-bundle"))
        workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
        assert remote.tags[decision.tag] == decision.source
        assert len(remote.writes) == 2


@pytest.mark.parametrize("uploaded", ["none", "wheel", "sdist", "complete"])
def test_retry_upload_and_finalization_preserve_identity(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, uploaded: str
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    git("tag", decision.tag)
    remote.candidate(decision, draft=True)
    expected = dict(remote.published[decision.version])
    suffix = {"none": ".absent", "wheel": ".whl", "sdist": ".tar.gz", "complete": ""}[
        uploaded
    ]
    remote.published[decision.version] = {
        name: value for name, value in expected.items() if name.endswith(suffix)
    }
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    assert Release.read(Path("release-plan.json")) == decision
    workflow_step("Reuse retained artifacts on retry", monkeypatch)
    assert "exists=true" in Path("outputs").read_text()
    workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    monkeypatch.setenv("TAG", decision.tag)
    workflow_step("Stage only verified missing distributions", monkeypatch)
    assert {
        p.name for p in Path("publish-dist").iterdir()
    } == expected.keys() - remote.published[decision.version].keys()
    for path in Path("publish-dist").iterdir():
        assert artifacts.digest(path) == expected[path.name]
    assert not remote.writes
    remote.published[decision.version] = expected
    workflow_step("Verify uploaded hashes", monkeypatch)
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert len(remote.writes) == 1
    remote.writes.clear()
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert not remote.writes


def test_tag_reservation_failure_cannot_rebuild_on_retry(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    make_bundle(decision, Path("release-bundle"))
    remote.fail_create = True
    with pytest.raises(OSError):
        workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    assert remote.tags[decision.tag] == decision.source
    remote.writes.clear()
    remote.fail_create = False
    with pytest.raises(ValueError, match="restore original"):
        workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    assert not remote.writes


def test_finalization_cannot_create_missing_reservation(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    make_bundle(decision, Path("release-bundle"))
    remote.published[decision.version] = artifacts.verify(
        Path("release-bundle"), decision.source, decision.tag
    )
    with pytest.raises(ValueError, match="reservation"):
        workflow_step("Publish the verified GitHub release", monkeypatch)
    assert not remote.writes


@pytest.mark.parametrize(
    "state",
    [
        "missing-assets",
        "corrupt-notes",
        "conflicting-tag",
        "github-error",
        "pypi-conflict",
    ],
)
def test_retry_evidence_failure_allows_no_publication_writes(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    git("tag", decision.tag)
    remote.candidate(decision, draft=True)
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    if state == "missing-assets":
        (remote.bundles[decision.tag] / "CHANGELOG.md").unlink()
    elif state == "corrupt-notes":
        (remote.bundles[decision.tag] / "CHANGELOG.md").write_text("changed")
    elif state == "conflicting-tag":
        remote.tags[decision.tag] = "other-source"
    elif state == "github-error":
        remote.errors.add("/git/ref/")
    elif state == "pypi-conflict":
        remote.published[decision.version][
            next(iter(remote.published[decision.version]))
        ] = "wrong-bytes"
    with pytest.raises((ValueError, OSError)):
        workflow_step("Reuse retained artifacts on retry", monkeypatch)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "release_artifacts",
                "stage",
                "--source",
                decision.source,
                "--tag",
                decision.tag,
            ],
        )
        artifacts.main()
    assert not remote.writes
    assert not Path("publish-dist").exists()


def test_workflow_serializes_and_gates_writes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert (
        "group: quackframe-publication\n  queue: max\n  cancel-in-progress: false"
        in text
    )
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.event == 'push'" in text
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in text
    )
    assert text.index("Reuse retained artifacts on retry") < text.index(
        "Stamp, build and check distributions"
    )
    assert (
        "if: steps.plan.outputs.release == 'true' && "
        "steps.retained.outputs.exists != 'true'" in text
    )
    assert "needs: [package, retain]" in text
    assert "needs: [package, publish]" in text
    assert "if: hashFiles('publish-dist/*') != ''" in text
    assert text.count("id-token: write") == 1


@pytest.mark.parametrize("field", ["SOURCE", "TAG"])
def test_retention_rejects_bundle_for_another_workflow_identity(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    make_bundle(decision, Path("release-bundle"))
    monkeypatch.setenv(field, "another-identity")
    with pytest.raises(ValueError, match="workflow"):
        workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    assert not remote.writes


def test_retry_rejects_conflicting_github_release_identity(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    git("tag", decision.tag)
    remote.candidate(decision, draft=True)
    remote.releases[decision.tag]["prerelease"] = False
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    with pytest.raises(ValueError, match="identity"):
        workflow_step("Reuse retained artifacts on retry", monkeypatch)
    assert not remote.writes


def test_new_release_finalizes_retained_draft(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote.releases["other-tool-v1"] = {
        "tag_name": "other-tool-v1",
        "draft": False,
        "prerelease": False,
    }
    commit("feat: initial delivery")
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    workflow_step("Reuse retained artifacts on retry", monkeypatch)
    workflow_step("Stamp, build and check distributions", monkeypatch)
    make_bundle(decision, Path("release-bundle"))
    workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    assert remote.releases[decision.tag]["draft"]
    assert (
        workflow.api(
            f"repos/example/quackframe/releases/tags/{decision.tag}", optional=True
        )
        is None
    )
    remote.published[decision.version] = artifacts.verify(
        Path("release-bundle"), decision.source, decision.tag
    )
    remote.writes.clear()
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert not remote.releases[decision.tag]["draft"]
    assert [write[2] for write in remote.writes] == ["edit"]
    remote.writes.clear()
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert not remote.writes


@pytest.mark.parametrize("selection", ["accepted", "mismatched", "missing"])
def test_workflow_uses_explicit_candidate_before_planning(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    change_file("delivery.txt", "feat: accepted delivery")
    candidate = plan("release/next")
    assert candidate
    git("tag", candidate.tag)
    remote.candidate(candidate)
    change_file("delivery.txt", "fix: later candidate change")
    later = plan("release/next")
    assert later
    git("tag", later.tag)
    remote.candidate(later)
    Path("delivery.txt").write_text("feat: accepted delivery", encoding="utf-8")
    git("add", "delivery.txt")
    commit("chore: restore accepted candidate tree")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote accepted candidate")
    selected = {
        "accepted": candidate.tag,
        "mismatched": later.tag,
        "missing": "v0.1.0-rc.99",
    }[selection]
    event_and_pr(remote, monkeypatch, candidate=selected)
    if selection != "accepted":
        with pytest.raises(ValueError, match=r"differs|absent"):
            workflow_step("Calculate or resume the release", monkeypatch)
        assert not Path("release-plan.json").exists()
        assert not remote.writes
        return
    workflow_step("Calculate or resume the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    assert decision.candidate_tag == candidate.tag
    assert decision.candidate_source == candidate.source
    assert decision.version == "0.1.0"
    workflow_step("Reuse retained artifacts on retry", monkeypatch)
    workflow_step("Stamp, build and check distributions", monkeypatch)
    assert Release.read(Path("release-bundle/release.json")) == decision
    make_bundle(decision, Path("release-bundle"))
    workflow_step("Retain exact artifacts before PyPI upload", monkeypatch)
    assert remote.tags[decision.tag] == decision.source


@pytest.mark.parametrize("operation", ["authorize", "retain", "finalize"])
@pytest.mark.parametrize("state", ["missing", "read-error", "ambiguous"])
def test_draft_lookup_failure_prevents_writes(
    history: Path,
    remote: Remote,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    state: str,
) -> None:
    commit("feat: initial delivery")
    decision = plan("release/next")
    assert decision
    remote.candidate(decision, draft=True)
    make_bundle(decision, Path("release-bundle"))
    if state == "missing":
        remote.releases.clear()
    elif state == "read-error":
        remote.errors.add("/releases?")
    else:
        remote.releases["duplicate"] = dict(remote.releases[decision.tag])
    step = {
        "authorize": "Reuse retained artifacts on retry",
        "retain": "Retain exact artifacts before PyPI upload",
        "finalize": "Publish the verified GitHub release",
    }[operation]
    Path("release-plan.json").write_text(json.dumps(asdict(decision)), encoding="utf-8")
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        workflow_step(step, monkeypatch)
    assert not remote.writes


@pytest.mark.parametrize("branch", ["main", "release/next"])
def test_workflow_maintenance_is_no_release_after_provenance(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, branch: str
) -> None:
    first_stable()
    if branch == "release/next":
        git("checkout", branch)
        git("merge", "main", "--no-edit")
    commit("docs: maintenance only")
    event_and_pr(remote, monkeypatch, head="docs/example")
    workflow_step("Calculate or resume the release", monkeypatch)
    assert "release=false" in Path("outputs").read_text()
    assert not Path("release-plan.json").exists()
    assert not remote.writes
