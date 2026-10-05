"""Execute the workflow's release gates and GitHub writes with verified evidence.

GitHub CLI and the PyPI hash reader are the only remote boundaries. The workflow
calls these same entrypoints in tests; no guard is duplicated in shell code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.release_artifacts import published_hashes, reconcile, verify
from scripts.release_identity import Flow, Release


def command(*args: str) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True
    ).stdout.strip()


def api(endpoint: str, *, optional: bool = False) -> Any:
    try:
        return json.loads(command("gh", "api", endpoint))
    except subprocess.CalledProcessError as exc:
        if optional and "(HTTP 404)" in (exc.stderr or ""):
            return None
        raise ValueError(f"Cannot verify GitHub evidence: {endpoint}") from exc


def pages(endpoint: str) -> list[dict[str, Any]]:
    result: list[list[dict[str, Any]]] = json.loads(
        command("gh", "api", endpoint, "--paginate", "--slurp")
    )
    return [item for page in result for item in page]


def github_release(repository: str, tag: str) -> dict[str, Any] | None:
    """Find retained evidence, including drafts, with the token's push access."""
    # GitHub's by-tag endpoint only finds published releases. Recovery must
    # inspect the authorized listing so an existing draft is not mistaken for loss.
    matches = [
        record
        for record in pages(f"repos/{repository}/releases?per_page=100")
        if record["tag_name"] == tag
    ]
    if len(matches) > 1:
        raise ValueError("Multiple GitHub releases claim the same tag.")
    return matches[0] if matches else None


def output(**values: str) -> None:
    if destination := os.environ.get("GITHUB_OUTPUT"):
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())


def workflow_plan(destination: Path) -> None:
    """Validate the CI source and merged PR provenance before saving a decision."""
    from scripts.release import git, plan

    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    run = event["workflow_run"]
    repository = os.environ["GITHUB_REPOSITORY"]
    branch, source = run["head_branch"], run["head_sha"]
    if not all(
        (
            os.environ.get("QUACKFRAME_RELEASES_ENABLED") == "true",
            run["conclusion"] == "success",
            run["event"] == "push",
            run["head_repository"]["full_name"] == repository,
            branch in {"main", "release/next"},
            source == git("rev-parse", "HEAD"),
        )
    ):
        output(release="false")
        return
    # Resolve the reviewed selection before planning; an implicit newest-RC
    # precheck can reject the exact tree of an explicitly accepted older RC.
    prs = pages(f"repos/{repository}/commits/{source}/pulls?per_page=100")
    merged = [
        pr
        for pr in prs
        if pr["merged_at"]
        and pr["merge_commit_sha"] == source
        and pr["base"]["ref"] == branch
        and pr["base"]["repo"]["full_name"] == repository
    ]
    if len(merged) != 1:
        raise ValueError(
            "Release source needs one verified merged PR; "
            "provenance is missing or ambiguous."
        )
    pr = merged[0]
    flow: Flow = "candidate" if branch == "release/next" else "patch"
    candidate: str | None = None
    if branch == "main" and pr["head"]["ref"] == "release/next":
        if not pr["head"]["repo"] or pr["head"]["repo"]["full_name"] != repository:
            raise ValueError(
                "Promotion must originate from this repository's release/next."
            )
        flow = "promotion"
        body = pr["body"] or ""
        candidates = re.findall(r"^Candidate: (v\d+\.\d+\.\d+-rc\.\d+)\s*$", body, re.M)
        if len(candidates) != 1 or not re.search(r"^Acceptance: \S.+$", body, re.M):
            raise ValueError(
                "Promotion PR must identify Candidate: and "
                "consuming-project Acceptance: evidence."
            )
        candidate = candidates[0]
    decision = plan(branch, flow=flow, candidate_tag=candidate)
    if decision is None:
        output(release="false")
        return
    destination.write_text(
        json.dumps(asdict(decision), indent=2) + "\n", encoding="utf-8"
    )
    output(
        release="true",
        tag=decision.tag,
        version=decision.version,
        prerelease=str(decision.prerelease).lower(),
    )


def verify_bundle(bundle: Path, release: Release) -> dict[str, str]:
    hashes = verify(bundle, release.source, release.tag)
    if Release.read(bundle / "release.json") != release:
        raise ValueError(
            "Retained release decision conflicts with the planned identity."
        )
    return hashes


def download(tag: str, destination: Path) -> None:
    command("gh", "release", "download", tag, "--dir", str(destination))


def verify_github_identity(record: dict[str, Any], release: Release) -> None:
    if record["prerelease"] != release.prerelease or record["tag_name"] != release.tag:
        raise ValueError("GitHub release identity conflicts with the decision.")


def candidate_published(release: Release, repository: str) -> None:
    if release.flow != "promotion":
        return
    candidate = release.candidate_tag
    record = api(f"repos/{repository}/releases/tags/{candidate}", optional=True)
    if (
        not record
        or record["draft"]
        or not record["prerelease"]
        or record["tag_name"] != candidate
    ):
        raise ValueError("Selected RC needs a completed GitHub prerelease.")
    if (
        api(f"repos/{repository}/commits/{candidate}")["sha"]
        != release.candidate_source
    ):
        raise ValueError(
            "Selected RC tag conflicts with the recorded candidate source."
        )
    with tempfile.TemporaryDirectory(prefix="quackframe-candidate-") as directory:
        bundle = Path(directory)
        download(str(candidate), bundle)
        hashes = verify(bundle, str(release.candidate_source), str(candidate))
        metadata = Release.read(bundle / "release.json")
        if metadata.flow != "candidate" or metadata.branch != "release/next":
            raise ValueError("Selected RC has conflicting retained candidate identity.")
        if reconcile(hashes, published_hashes(metadata.version)):
            raise ValueError("Selected RC publication on PyPI is incomplete.")


def authorize(release: Release, bundle: Path, repository: str) -> None:
    """Gate new builds and retries before any version reservation or upload."""
    pending = [
        r["tag_name"]
        for r in pages(f"repos/{repository}/releases?per_page=100")
        if r["draft"]
    ]
    if any(tag != release.tag for tag in pending):
        raise ValueError(
            "An earlier publication needs recovery before another release."
        )
    candidate_published(release, repository)
    # A remote tag is a reservation even when its GitHub release is missing.
    tagged = api(f"repos/{repository}/git/ref/tags/{release.tag}", optional=True)
    if tagged is not None:
        if api(f"repos/{repository}/commits/{release.tag}")["sha"] != release.source:
            raise ValueError("Reserved tag belongs to another source.")
        record = github_release(repository, release.tag)
        if record is None:
            raise ValueError("Reserved tag lacks retained GitHub release evidence.")
        verify_github_identity(record, release)
        download(release.tag, bundle)
        verify_bundle(bundle, release)
        output(exists="true")


def retain(release: Release, bundle: Path, repository: str) -> None:
    """Reserve a new identity once; retries require the original retained bundle."""
    verify_bundle(bundle, release)
    candidate_published(release, repository)
    tagged = api(f"repos/{repository}/git/ref/tags/{release.tag}", optional=True)
    record = github_release(repository, release.tag)
    if tagged is not None:
        if api(f"repos/{repository}/commits/{release.tag}")["sha"] != release.source:
            raise ValueError("Reserved tag belongs to another source.")
        if record is None:
            raise ValueError(
                "Reserved tag lacks retained evidence; "
                "restore original assets through reviewed recovery."
            )
        verify_github_identity(record, release)
        with tempfile.TemporaryDirectory(prefix="quackframe-retained-") as directory:
            retained = Path(directory)
            download(release.tag, retained)
            verify_bundle(retained, release)
            if (retained / "SHA256SUMS.json").read_bytes() != (
                bundle / "SHA256SUMS.json"
            ).read_bytes():
                raise ValueError("Retained artifacts conflict with this bundle.")
        return
    if record is not None:
        raise ValueError("GitHub release exists without its reserved tag.")
    command(
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{repository}/git/refs",
        "-f",
        f"ref=refs/tags/{release.tag}",
        "-f",
        f"sha={release.source}",
    )
    command(
        "gh",
        "release",
        "create",
        release.tag,
        *[str(p) for p in sorted(bundle.iterdir())],
        "--target",
        release.source,
        "--draft",
        "--title",
        release.tag,
        "--notes-file",
        str(bundle / "CHANGELOG.md"),
        *(["--prerelease"] if release.prerelease else []),
    )


def finalize(release: Release, bundle: Path, repository: str) -> None:
    """Verify the remote tag, retained bytes and PyPI before completing GitHub."""
    if api(f"repos/{repository}/git/ref/tags/{release.tag}", optional=True) is None:
        raise ValueError("Finalization requires the original tag reservation.")
    retain(release, bundle, repository)
    if reconcile(verify_bundle(bundle, release), published_hashes(release.version)):
        raise ValueError("PyPI publication incomplete; cannot finalize.")
    record = github_release(repository, release.tag)
    if record is None:
        raise ValueError("Retained GitHub release disappeared before finalization.")
    verify_github_identity(record, release)
    if not record["draft"]:
        return
    command(
        "gh",
        "release",
        "edit",
        release.tag,
        "--draft=false",
        "--prerelease" if release.prerelease else "--prerelease=false",
        "--latest=false" if release.prerelease else "--latest",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["plan", "authorize", "prepare", "retain", "finalize"]
    )
    parser.add_argument("--decision", type=Path, default=Path("release-plan.json"))
    parser.add_argument("--bundle", type=Path, default=Path("release-bundle"))
    args = parser.parse_args()
    if args.operation == "plan":
        workflow_plan(args.decision)
        return
    release = Release.read(args.decision)
    for name, expected in (("SOURCE", release.source), ("TAG", release.tag)):
        if name in os.environ and os.environ[name] != expected:
            raise ValueError(f"Release decision differs from the workflow {name}.")
    if args.operation == "prepare":
        from scripts.release import prepare

        prepare(release, args.bundle)
        return
    operations = {"authorize": authorize, "retain": retain, "finalize": finalize}
    operations[args.operation](release, args.bundle, os.environ["GITHUB_REPOSITORY"])


if __name__ == "__main__":
    main()
