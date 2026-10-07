"""Exercise real release-tool calculations against isolated Git histories."""

import json
import tomllib
from pathlib import Path

import pytest

from scripts.release import git, plan, prepare

PROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


@pytest.fixture
def history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_bytes(PROJECT.read_bytes())
    git("init", "-b", "main")
    git("config", "user.email", "release-test@example.invalid")
    git("config", "user.name", "Release Test")
    git("remote", "add", "origin", "https://github.com/example/quackframe.git")
    git("add", ".")
    git("commit", "-m", "chore: scaffold")
    git("checkout", "-b", "release/next")
    return tmp_path


def commit(message: str) -> None:
    git("commit", "--allow-empty", "-m", message)


def tag_release(branch: str, expected: str) -> str:
    release = plan(branch)
    assert release is not None
    assert release.version == expected
    git("tag", release.tag)
    return release.tag


def first_stable() -> None:
    commit("feat: first implementation")
    tag_release("release/next", "0.1.0rc1")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore(release): promote 0.1.0")
    tag_release("main", "0.1.0")


def test_candidate_promotion_patch_and_concurrent_next_minor(history: Path) -> None:
    first_stable()
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    assert plan("release/next") is None
    commit("feat: next feature")
    tag_release("release/next", "0.2.0rc1")
    commit("fix: candidate correction")
    tag_release("release/next", "0.2.0rc2")

    git("checkout", "main")
    change_file("stable-fix.txt", "fix: stable correction")
    tag_release("main", "0.1.1")
    git("checkout", "release/next")
    with pytest.raises(ValueError, match="Synchronize"):
        plan("release/next")
    git("merge", "--no-ff", "main", "-m", "chore: synchronize stable")
    # The stable fix is already released; synchronization alone is not a new RC.
    assert plan("release/next") is None
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote stale candidate")
    with pytest.raises(ValueError, match="differs"):
        plan("main")
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    assert plan("release/next") is None
    commit("feat: another candidate feature")
    tag_release("release/next", "0.2.0rc3")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore(release): promote 0.2.0")
    tag_release("main", "0.2.0")


@pytest.mark.parametrize("message", ["feat: initial", "fix: initial", "feat!: initial"])
def test_first_release_has_explicit_target(history: Path, message: str) -> None:
    commit(message)
    tag_release("release/next", "0.1.0rc1")


@pytest.mark.parametrize(
    "message", ["docs: clarify", "refactor: simplify", "chore: sync"]
)
def test_maintenance_does_not_release(history: Path, message: str) -> None:
    commit(message)
    assert plan("release/next") is None


def test_retry_resumes_original_version(history: Path) -> None:
    commit("feat: initial")
    original = tag_release("release/next", "0.1.0rc1")
    resumed = plan("release/next")
    assert resumed is not None
    assert resumed.tag == original


def test_direct_feature_on_main_is_rejected(history: Path) -> None:
    first_stable()
    commit("feat: untested feature")
    with pytest.raises(ValueError, match="published RC"):
        plan("main")


def test_promotion_requires_exact_candidate_tree(history: Path) -> None:
    commit("feat: first implementation")
    tag_release("release/next", "0.1.0rc1")
    (history / "unreviewed.txt").write_text("different code", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "fix: untested change")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    with pytest.raises(ValueError, match="differs"):
        plan("main")


def test_prepare_stamps_pep440_without_git_mutations(history: Path) -> None:
    import tomllib

    commit("feat: initial")
    source = git("rev-parse", "HEAD")
    release = plan("release/next")
    assert release is not None
    prepare(release, history / "bundle")
    assert git("rev-parse", "HEAD") == source
    assert git("tag", "--list") == ""
    with Path("pyproject.toml").open("rb") as stream:
        assert tomllib.load(stream)["project"]["version"] == "0.1.0rc1"
    assert (history / "bundle" / "CHANGELOG.md").is_file()


def test_other_branches_cannot_publish(history: Path) -> None:
    with pytest.raises(ValueError, match="Only"):
        plan("feature/example")


def test_breaking_change_during_zero_stays_on_minor_line(history: Path) -> None:
    first_stable()
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    commit("feat!: change SQL signature\n\nBREAKING CHANGE: update arguments")
    tag_release("release/next", "0.2.0rc1")


def test_maintenance_after_rc_does_not_publish(history: Path) -> None:
    commit("feat: initial")
    tag_release("release/next", "0.1.0rc1")
    commit("docs: clarify installation")
    assert plan("release/next") is None


def test_stable_feature_release_after_one_uses_major_bump(history: Path) -> None:
    first_stable()
    git("tag", "v1.0.0")
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    commit("feat!: incompatible stable contract")
    tag_release("release/next", "2.0.0rc1")


def test_synchronization_cannot_resume_an_already_promoted_rc(history: Path) -> None:
    commit("feat: initial")
    tag_release("release/next", "0.1.0rc1")
    git("checkout", "main")
    git("merge", "--ff-only", "release/next")
    tag_release("main", "0.1.0")
    git("checkout", "release/next")
    assert plan("release/next") is None


def change_file(name: str, message: str) -> None:
    Path(name).parent.mkdir(parents=True, exist_ok=True)
    Path(name).write_text(message, encoding="utf-8")
    git("add", name)
    commit(message)


def prepare_and_check(branch: str, version: str, descriptions: list[str]) -> str:
    release = plan(branch)
    assert release is not None
    assert release.version == version
    prepare(release, Path("bundle"))
    notes = Path("bundle/CHANGELOG.md").read_text(encoding="utf-8")
    assert release.tag[1:] in notes
    for description in descriptions:
        assert description.lower() in notes.lower()
    metadata = json.loads(Path("bundle/release.json").read_text(encoding="utf-8"))
    assert metadata["version"] == version
    assert metadata["source"] == git("rev-parse", "HEAD")
    assert (
        tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
        == version
    )
    git("restore", "pyproject.toml")
    return release.tag


@pytest.mark.parametrize("kind", ["feat", "fix", "perf", "feat!"])
def test_bootstrap_through_second_candidate_and_stable(
    history: Path, kind: str
) -> None:
    change_file("first.txt", f"{kind}: delivered behaviour")
    prepare_and_check("release/next", "0.1.0rc1", ["delivered behaviour"])
    tag_release("release/next", "0.1.0rc1")
    change_file("second.txt", f"{kind}: candidate correction")
    prepare_and_check(
        "release/next", "0.1.0rc2", ["delivered behaviour", "candidate correction"]
    )
    tag_release("release/next", "0.1.0rc2")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    prepare_and_check("main", "0.1.0", ["delivered behaviour", "candidate correction"])
    tag_release("main", "0.1.0")
    change_file("patch.txt", "fix: stable correction")
    prepare_and_check("main", "0.1.1", ["stable correction"])


MERGE_MESSAGES = [
    "feat: introduce new API",
    "fix!: remove old API",
    "fix: remove old API\n\nBREAKING CHANGE: migrate calls",
    "fix!: remove old API\n\nBREAKING CHANGE: migrate calls",
]


@pytest.mark.parametrize("message", MERGE_MESSAGES)
@pytest.mark.parametrize("stable", ["0.1.0", "1.0.0"])
@pytest.mark.parametrize("child", ["fix", "chore"])
def test_qualifying_merge_cannot_escape_as_direct_patch(
    history: Path, message: str, stable: str, child: str
) -> None:
    first_stable()
    if stable == "1.0.0":
        git("tag", "v1.0.0")
    git("checkout", "-b", "fix/example")
    change_file("fix.txt", f"{child}: ordinary child correction")
    git("checkout", "main")
    git("merge", "--no-ff", "fix/example", "-m", message)
    with pytest.raises(ValueError, match="published RC"):
        plan("main")

    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    expected = (
        "0.2.0rc1"
        if stable == "0.1.0"
        else ("1.1.0rc1" if message.startswith("feat:") else "2.0.0rc1")
    )
    descriptions = [message.splitlines()[0].split(": ")[1], "ordinary child correction"]
    if "BREAKING CHANGE" in message:
        descriptions.append("migrate calls")
    prepare_and_check("release/next", expected, descriptions)


def test_initial_candidate_and_stable_notes_describe_delivery(history: Path) -> None:
    change_file("feature.txt", "feat: implement SQL workflows")
    change_file("fix.txt", "fix: preserve session ownership")
    change_file(
        "migration.txt", "feat!: replace calls\n\nBREAKING CHANGE: migrate calls"
    )
    descriptions = [
        "implement SQL workflows",
        "preserve session ownership",
        "migrate calls",
    ]
    tag = prepare_and_check("release/next", "0.1.0rc1", descriptions)
    git("tag", tag)
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    prepare_and_check("main", "0.1.0", descriptions)


@pytest.mark.parametrize(
    "filename", ["guide.md", "code.py", ".github/workflows/test.yml"]
)
def test_patch_promotion_cannot_include_changes_after_candidate(
    history: Path, filename: str
) -> None:
    first_stable()
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    change_file("fix.txt", "fix: candidate correction")
    tag_release("release/next", "0.1.1rc1")
    change_file(filename, "docs: change after candidate")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote patch")
    with pytest.raises(ValueError, match="differs"):
        release = plan("main")
        assert release is not None
        prepare(release, Path("bundle"))
    assert not Path("bundle/release.json").exists()


@pytest.mark.parametrize("target", ["0.1.1", "0.2.0", "2.0.0"])
@pytest.mark.parametrize("changed", ["", "docs", "code", "workflow", "resolution"])
def test_promotion_target_and_freshness(
    history: Path, target: str, changed: str
) -> None:
    first_stable()
    if target == "2.0.0":
        git("tag", "v1.0.0")
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    kind = {"0.1.1": "fix", "0.2.0": "feat", "2.0.0": "feat!"}[target]
    change_file("delivery.txt", f"{kind}: deliver candidate")
    selected = tag_release("release/next", f"{target}rc1")
    if changed in {"docs", "code", "workflow"}:
        filename = {
            "docs": "guide.md",
            "code": "feature.py",
            "workflow": ".github/workflows/ci.yml",
        }[changed]
        change_file(filename, "docs: changed candidate tree")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    if changed == "resolution":
        change_file("resolution.txt", "chore: merge resolution")
    if changed:
        with pytest.raises(ValueError, match="differs"):
            plan("main", flow="promotion", candidate_tag=selected)
        assert not Path("bundle/release.json").exists()
        git("checkout", "release/next")
        git("merge", "main", "--no-edit")
        change_file("fresh.txt", "fix: validate refreshed candidate")
        selected = tag_release("release/next", f"{target}rc2")
        git("checkout", "main")
        git(
            "merge",
            "--no-ff",
            "release/next",
            "-m",
            "chore: promote refreshed candidate",
        )
    decision = plan("main", flow="promotion", candidate_tag=selected)
    assert decision and decision.flow == "promotion"
    assert decision.candidate_tag == selected
    assert decision.candidate_source == git("rev-list", "-n", "1", selected)
    assert decision.version == target
    prepare_and_check("main", target, ["deliver candidate"])


@pytest.mark.parametrize("stable", ["0.1.0", "1.0.0"])
@pytest.mark.parametrize(
    "message", [*MERGE_MESSAGES, "fix: compatible", "perf: faster"]
)
def test_ordinary_commit_classification_and_mixed_range(
    history: Path, stable: str, message: str
) -> None:
    first_stable()
    if stable == "1.0.0":
        git("tag", "v1.0.0")
    git("checkout", "release/next")
    git("merge", "main", "--no-edit")
    commit("chore: maintenance")
    change_file("performance.txt", "perf: faster execution")
    change_file("implementation.txt", message)
    breaking = "!" in message or "BREAKING CHANGE" in message
    target = (
        ("0.2.0" if stable == "0.1.0" else "2.0.0")
        if breaking
        else (
            ("0.2.0" if stable == "0.1.0" else "1.1.0")
            if message.startswith("feat:")
            else ("0.1.1" if stable == "0.1.0" else "1.0.1")
        )
    )
    prepare_and_check(
        "release/next", target + "rc1", [message.splitlines()[0].split(": ")[1]]
    )


@pytest.mark.parametrize(
    "message",
    [
        "docs: clarify",
        "test: coverage",
        "build: metadata",
        "ci: checks",
        "chore(release): 0.1.0",
        "refactor: simplify",
        "docs: squash\n\n* feat: embedded feature",
    ],
)
def test_maintenance_and_squash_body_do_not_authorize_release(
    history: Path, message: str
) -> None:
    change_file("maintenance.txt", message)
    assert plan("release/next") is None


def test_version_file_edit_alone_does_not_release(history: Path) -> None:
    text = PROJECT.read_text().replace('version = "0.1.0"', 'version = "9.9.9"', 1)
    change_file("pyproject.toml", text)
    assert plan("release/next") is None


def test_squash_uses_final_classification_without_replaying_embedded_commits(
    history: Path,
) -> None:
    first_stable()
    change_file("fix.txt", "fix: compatible squash (#23)\n\n* feat: embedded history")
    decision = plan("main")
    assert decision and decision.flow == "patch"
    assert decision.version == "0.1.1"


def test_bootstrap_rejects_conflicting_tag_history(history: Path) -> None:
    commit("fix: first correction")
    git("tag", "v0.2.0-rc.1")
    commit("fix: another correction")
    with pytest.raises(ValueError, match="bootstrap"):
        plan("release/next")


def test_preparation_rejects_changed_decision_and_reserved_rebuild(
    history: Path,
) -> None:
    from dataclasses import replace

    commit("feat: first implementation")
    decision = plan("release/next")
    assert decision
    with pytest.raises(ValueError, match="decision changed"):
        prepare(
            replace(decision, tag="v0.1.0-rc.2", version="0.1.0rc2"), Path("bundle")
        )
    assert not Path("bundle").exists()
    git("tag", decision.tag)
    with pytest.raises(ValueError, match="reuse retained"):
        prepare(decision, Path("bundle"))
    commit("fix: later source")
    with pytest.raises(ValueError, match="source changed"):
        prepare(decision, Path("bundle"))


def test_selected_candidate_is_not_silently_substituted(history: Path) -> None:
    commit("feat: first implementation")
    tag_release("release/next", "0.1.0rc1")
    change_file("fix.txt", "fix: changed source")
    latest = tag_release("release/next", "0.1.0rc2")
    git("checkout", "main")
    git("merge", "--no-ff", "release/next", "-m", "chore: promote")
    with pytest.raises(ValueError, match="differs"):
        plan("main", flow="promotion", candidate_tag="v0.1.0-rc.1")
    with pytest.raises(ValueError, match="absent"):
        plan("main", flow="promotion", candidate_tag="v0.1.0-rc.99")
    assert plan("main", flow="promotion", candidate_tag=latest)
