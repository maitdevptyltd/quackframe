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
from dataclasses import asdict, dataclass, field, replace
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
    command_line = command_line.replace("$GITHUB_WORKSPACE/", "")
    command_line = command_line.replace(
        "decision/release-plan.json", "release-plan.json"
    )
    for name in ("SOURCE", "TAG"):
        command_line = command_line.replace(f"${name}", os.environ.get(name, ""))
    arguments = shlex.split(command_line)
    if arguments[0] == "poetry":
        arguments = arguments[arguments.index("run") + 1 :]
    assert arguments[:2] == ["python", "-I"]
    assert arguments[2].endswith("scripts/release_entrypoint.py")
    arguments = arguments[3:]
    if arguments[0] == "--repository":
        arguments = arguments[2:]
    assert arguments[0] in {"release_workflow", "release_artifacts"}
    if (
        arguments[1] in {"stage", "verify", "finalize"}
        and "PLANNED_RELEASE" not in os.environ
    ):
        # Supply the planner output separately from the downloaded build bundle.
        decision = Path("release-plan.json")
        if not decision.exists():
            decision = Path("release-bundle/release.json")
        monkeypatch.setenv("PLANNED_RELEASE", decision.read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", arguments)
    if arguments[0] == "release_workflow":
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

    def hashes(self, version: str) -> dict[str, str]:
        if "pypi" in self.errors:
            raise OSError("PyPI evidence unavailable")
        return self.published.get(version, {})

    def command(self, *args: str) -> str:
        assert args[0] == "gh", args
        if args[1] == "api":
            endpoint = args[2]
            if any(error in endpoint for error in self.errors):
                raise subprocess.CalledProcessError(1, args, stderr="HTTP 503")
            if "/pulls?" in endpoint:
                return json.dumps([self.prs])
            tag = endpoint.split("/tags/")[-1]
            if "/git/ref/tags/" in endpoint and tag in self.tags:
                return json.dumps({"object": {"sha": self.tags[tag]}})
            # GitHub's by-tag endpoint only exposes published releases.
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
                raise ValueError("Release assets are missing")
            shutil.copytree(self.bundles[tag], Path(args[5]), dirs_exist_ok=True)
        elif operation == "create":
            self.writes.append(args)
            self.tags[tag] = args[args.index("--target") + 1]
            destination = self.root / tag
            destination.mkdir()
            for filename in args[4 : args.index("--target")]:
                shutil.copy2(filename, destination)
            self.bundles[tag] = destination
            self.releases[tag] = {
                "tag_name": tag,
                "draft": False,
                "prerelease": "--prerelease" in args,
            }
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
            "body": "Consumer smoke passed for the latest candidate.",
        }
    ]
    return run


@pytest.mark.parametrize("head", ["fix/example", "release/next"])
def test_patch_provenance_cannot_silently_fall_back(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    first_stable()
    change_file("fix.txt", "fix: stable correction")
    event_and_pr(remote, monkeypatch, head=head)
    if head == "release/next":
        with pytest.raises(ValueError, match="published RC"):
            workflow_step("Calculate the release", monkeypatch)
    else:
        workflow_step("Calculate the release", monkeypatch)
        decision = Release.read(Path("release-plan.json"))
        assert decision.flow == "patch"
        assert decision.version == "0.1.1"
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
    Path("event.json").write_text(json.dumps({"workflow_run": run}), encoding="utf-8")
    if invalid in {
        "missing-pr",
        "ambiguous-pr",
        "superseded",
    }:
        with pytest.raises(ValueError):
            workflow_step("Calculate the release", monkeypatch)
    else:
        workflow_step("Calculate the release", monkeypatch)
        assert "release=false" in Path("outputs").read_text()
    assert not Path("release-plan.json").exists()
    assert not remote.writes


def test_release_workflow_limits_token_exposure_and_job_duration() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    sections = re.split(r"^  (\w+):$", text.split("jobs:\n", 1)[1], flags=re.M)
    jobs = dict(zip(sections[1::2], sections[2::2], strict=True))
    token_steps = {
        "Calculate the release",
        "Publish the verified GitHub release",
    }
    found_token_steps: set[str] = set()
    for job in jobs.values():
        settings, steps = job.split("    steps:\n", 1)
        assert "GH_TOKEN" not in settings
        timeout = re.search(r"^    timeout-minutes: (\d+)$", settings, re.M)
        assert timeout and 1 <= int(timeout[1]) <= 30
        for step in re.split(r"^      - ", steps, flags=re.M)[1:]:
            assert "permissions:" not in step
            if "GH_TOKEN:" in step:
                name = step.splitlines()[0].removeprefix("name: ")
                found_token_steps.add(name)
                assert name in token_steps
            if "uses: actions/checkout@" in step:
                assert "persist-credentials: false" in step
    assert found_token_steps == token_steps


def test_privileged_release_actions_use_verified_commit_pins() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pins = {
        "actions/create-github-app-token": (
            "64ab729a6294000f5aa4a4bc0b73d1f32bc45510",
            "v3.3.0",
            1,
        ),
        "pypa/gh-action-pypi-publish": (
            "dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
            "v1.14.2",
            1,
        ),
    }
    for action, (sha, version, count) in pins.items():
        refs = re.findall(rf"uses: {re.escape(action)}@(.+)", text)
        assert refs == [f"{sha} # {version}"] * count


def test_candidate_build_is_separate_from_trusted_release_jobs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    # Split only job headings, not step or environment mappings.
    sections = re.split(r"^  (plan|package|publish|finalize):$", text, flags=re.M)
    jobs = dict(zip(sections[1::2], sections[2::2], strict=True))
    assert "github.ref == 'refs/heads/main'" in jobs["plan"]
    assert "decision: ${{ steps.plan.outputs.decision }}" in jobs["plan"]
    for name, job in jobs.items():
        assert "ref: ${{ github.sha }}" in job
        assert "persist-credentials: true" not in job
        if name in {"publish", "finalize"}:
            assert "environment: pypi" in job
            assert "workflow_run.head_sha }}\n          persist" not in job
            assert "ref: ${{ github.event.workflow_run." not in job
            assert "poetry" not in job
            assert "python -I scripts/release_entrypoint.py" in job
        if name in {"publish", "finalize"}:
            assert "PLANNED_RELEASE: ${{ needs.plan.outputs.decision }}" in job
            assert "--decision release-bundle/" not in job
        if name != "publish":
            assert "id-token: write" not in job
    build = jobs["package"]
    assert "contents: read" in build
    assert all(value not in build for value in ("secrets.", "environment:", "GH_TOKEN"))
    assert "outputs:" not in build
    assert "poetry -C tooling install --no-root" in jobs["plan"]
    assert "--repository" in jobs["plan"]
    assert "build --no-isolation" not in jobs["plan"]
    assert "package_smoke" not in jobs["plan"]


def test_trusted_entrypoint_ignores_candidate_import_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "scripts").mkdir()
    sentinel = tmp_path / "candidate-executed"
    payload = (
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
        "raise RuntimeError('candidate executed')\n"
    )
    for path in (
        candidate / "scripts/__init__.py",
        candidate / "scripts/release_artifacts.py",
        candidate / "json.py",
        candidate / "sitecustomize.py",
    ):
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(candidate))
    release = Release(
        "synthetic-source", "release/next", "v0.1.0-rc.1", "0.1.0rc1", True, "candidate"
    )
    bundle = make_bundle(release, tmp_path / "bundle")
    entrypoint = WORKFLOW.parents[2] / "scripts/release_entrypoint.py"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(entrypoint),
            "--repository",
            str(candidate),
            "release_artifacts",
            "verify-local",
            "--bundle",
            str(bundle),
            "--source",
            release.source,
            "--tag",
            release.tag,
        ],
        cwd=candidate,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


def test_planner_uses_trusted_policy_with_candidate_history(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Path("pyproject.toml")
    candidate_policy = project.read_text().replace(
        'tag_format = "v{version}"', 'tag_format = "untrusted-{version}"'
    )
    change_file("pyproject.toml", candidate_policy)
    commit("feat: candidate delivery")
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    assert decision.source == git("rev-parse", "HEAD")
    assert decision.tag == "v0.1.0-rc.1"
    outputs = Path("outputs").read_text()
    assert f"decision={json.dumps(asdict(decision))}" in outputs


@pytest.mark.parametrize("operation", ["stage", "verify", "finalize"])
@pytest.mark.parametrize("substitution", ["source", "version", "flow"])
def test_build_cannot_replace_trusted_release_decision(
    history: Path,
    remote: Remote,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    substitution: str,
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    remote.candidate(decision, draft=True)
    forged = {
        "source": replace(decision, source="other-source"),
        "version": replace(decision, tag="v9.9.9-rc.1", version="9.9.9rc1"),
        "flow": replace(
            decision,
            branch="main",
            tag="v9.9.9",
            version="9.9.9",
            prerelease=False,
            flow="patch",
        ),
    }[substitution]
    make_bundle(forged, Path("release-bundle"))
    monkeypatch.setenv("PLANNED_RELEASE", json.dumps(asdict(decision)))
    monkeypatch.setenv("SOURCE", decision.source)
    monkeypatch.setenv("TAG", decision.tag)
    step = {
        "stage": "Stage only verified missing distributions",
        "verify": "Verify uploaded hashes",
        "finalize": "Publish the verified GitHub release",
    }[operation]
    with pytest.raises(ValueError, match="another source or version"):
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
    workflow_step("Calculate the release", monkeypatch)
    assert "release=false" in Path("outputs").read_text()
    assert not Path("release-plan.json").exists()
    assert not remote.writes


@pytest.mark.parametrize("uploaded", ["none", "wheel", "sdist", "complete"])
def test_original_build_retries_only_missing_uploads(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, uploaded: str
) -> None:
    commit("feat: initial")
    event_and_pr(remote, monkeypatch, head="feat/example")
    workflow_step("Calculate the release", monkeypatch)
    decision = Release.read(Path("release-plan.json"))
    bundle = make_bundle(decision, Path("release-bundle"))
    expected = artifacts.verify(bundle, decision.source, decision.tag)
    suffix = {"wheel": ".whl", "sdist": ".tar.gz"}.get(uploaded, "")
    remote.published[decision.version] = {
        name: value
        for name, value in expected.items()
        if uploaded == "complete" or (suffix and name.endswith(suffix))
    }
    workflow_step("Stage only verified missing distributions", monkeypatch)
    assert {p.name for p in Path("publish-dist").iterdir()} == (
        expected.keys() - remote.published[decision.version].keys()
    )
    for path in Path("publish-dist").iterdir():
        assert artifacts.digest(path) == expected[path.name]
    assert not remote.writes
    remote.published[decision.version] = expected
    workflow_step("Verify uploaded hashes", monkeypatch)
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert remote.tags[decision.tag] == decision.source
    assert not remote.releases[decision.tag]["draft"]
    assert len(remote.writes) == 1
    remote.writes.clear()
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert not remote.writes


@pytest.mark.parametrize(
    "state", ["partial", "conflict", "tag-only", "wrong-tag", "unrelated-draft"]
)
def test_finalization_requires_published_bytes_and_matching_tag(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    commit("feat: initial")
    decision = plan("release/next")
    assert decision
    bundle = make_bundle(decision, Path("release-bundle"))
    remote.published[decision.version] = artifacts.verify(
        bundle, decision.source, decision.tag
    )
    if state == "partial":
        remote.published[decision.version].pop(
            next(iter(remote.published[decision.version]))
        )
    elif state == "conflict":
        remote.published[decision.version][
            next(iter(remote.published[decision.version]))
        ] = "wrong"
    elif state in {"tag-only", "wrong-tag"}:
        remote.tags[decision.tag] = decision.source if state == "tag-only" else "other"
    else:
        remote.releases["unrelated"] = {"draft": True}
    if state in {"partial", "conflict", "wrong-tag"}:
        with pytest.raises(ValueError):
            workflow_step("Publish the verified GitHub release", monkeypatch)
        assert not remote.writes
    else:
        workflow_step("Publish the verified GitHub release", monkeypatch)
        assert len(remote.writes) == 1


@pytest.mark.parametrize(
    "state",
    [
        "complete",
        "tag-only",
        "draft",
        "partial",
        "source-conflict",
        "hash-conflict",
        "github-error",
        "pypi-error",
    ],
)
def test_promotion_requires_completed_candidate_without_pr_body_fields(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    change_file("feature.txt", "feat: initial")
    candidate = plan("release/next")
    assert candidate
    git("tag", candidate.tag)
    remote.candidate(candidate)
    if state == "tag-only":
        remote.releases.clear()
    elif state == "draft":
        remote.releases[candidate.tag]["draft"] = True
    elif state == "partial":
        remote.published[candidate.version].pop(
            next(iter(remote.published[candidate.version]))
        )
    elif state == "source-conflict":
        remote.tags[candidate.tag] = "wrong"
    elif state == "hash-conflict":
        remote.published[candidate.version][
            next(iter(remote.published[candidate.version]))
        ] = "wrong"
    elif state == "github-error":
        remote.errors.add("/releases/tags/")
    elif state == "pypi-error":
        remote.errors.add("pypi")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    event_and_pr(remote, monkeypatch)
    remote.prs[0]["body"] = None
    if state == "complete":
        workflow_step("Calculate the release", monkeypatch)
        decision = Release.read(Path("release-plan.json"))
        assert decision.candidate_tag == candidate.tag
        assert decision.candidate_source == candidate.source
    else:
        with pytest.raises((ValueError, OSError)):
            workflow_step("Calculate the release", monkeypatch)
        assert not Path("release-plan.json").exists()
    assert not remote.writes


def test_workflow_builds_once_then_publishes_before_tagging() -> None:
    text = WORKFLOW.read_text()
    assert (
        "group: quackframe-publication\n  queue: max\n  cancel-in-progress: false"
        in text
    )
    assert "needs: [plan, package]" in text
    assert "needs: [plan, publish]" in text
    assert "retention-days: 90" in text
    assert "retained" not in text
    assert "release_artifacts seal" not in text
    assert "package_smoke" in text
    assert "contents: write" not in text.split("  package:")[0]
    assert "if: hashFiles('publish-dist/*') != ''" in text


def test_rerun_all_jobs_fails_explicitly_before_rebuilding(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("feat: initial")
    event_and_pr(remote, monkeypatch, head="feat/example")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with pytest.raises(ValueError, match="Rerun failed jobs"):
        workflow_step("Calculate the release", monkeypatch)
    assert not Path("release-plan.json").exists()
    assert not remote.writes


@pytest.mark.parametrize("matching", [True, False])
def test_promotion_uses_latest_rc_and_ignores_old_pr_selection(
    history: Path, remote: Remote, monkeypatch: pytest.MonkeyPatch, matching: bool
) -> None:
    change_file("feature.txt", "feat: first")
    first = plan("release/next")
    assert first
    git("tag", first.tag)
    remote.candidate(first)
    change_file("feature.txt", "fix: second")
    latest = plan("release/next")
    assert latest
    git("tag", latest.tag)
    remote.candidate(latest)
    if not matching:
        change_file("feature.txt", "chore: different untested tree")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    event_and_pr(remote, monkeypatch)
    remote.prs[0]["body"] = f"Candidate: {first.tag}"
    if matching:
        workflow_step("Calculate the release", monkeypatch)
        assert Release.read(Path("release-plan.json")).candidate_tag == latest.tag
    else:
        with pytest.raises(ValueError, match="differs from the tested RC"):
            workflow_step("Calculate the release", monkeypatch)
    assert not remote.writes


def test_failed_github_creation_retries_original_verified_build(
    remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    release = Release(
        "source", "release/next", "v0.1.0-rc.1", "0.1.0rc1", True, "candidate"
    )
    bundle = make_bundle(release, Path("release-bundle"))
    remote.published[release.version] = artifacts.verify(
        bundle, release.source, release.tag
    )
    original_hashes = dict(remote.published[release.version])

    def fail_creation(*args: str) -> str:
        if args[1:3] == ("release", "create"):
            raise subprocess.CalledProcessError(
                1, args, stderr="transient GitHub failure"
            )
        return remote.command(*args)

    monkeypatch.setattr(workflow, "command", fail_creation)
    with pytest.raises(subprocess.CalledProcessError):
        workflow_step("Publish the verified GitHub release", monkeypatch)
    assert remote.tags == {}
    assert remote.published[release.version] == original_hashes
    monkeypatch.setattr(workflow, "command", remote.command)
    workflow_step("Publish the verified GitHub release", monkeypatch)
    assert remote.tags[release.tag] == release.source
    assert artifacts.verify(bundle, release.source, release.tag) == original_hashes


def test_conflicting_pypi_bytes_stop_staging_without_upload(
    remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    release = Release(
        "source", "release/next", "v0.1.0-rc.1", "0.1.0rc1", True, "candidate"
    )
    bundle = make_bundle(release, Path("release-bundle"))
    hashes = artifacts.verify(bundle, release.source, release.tag)
    remote.published[release.version] = {next(iter(hashes)): "conflicting"}
    with pytest.raises(ValueError, match="conflicting artifact"):
        workflow_step("Stage only verified missing distributions", monkeypatch)
    assert not Path("publish-dist").exists()
    assert remote.writes == []
