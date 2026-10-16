"""Execute the workflow's release gates and GitHub writes with verified evidence.

GitHub CLI and the PyPI hash reader are the only remote boundaries. The workflow
calls these same entrypoints in tests; no guard is duplicated in shell code.
"""

from __future__ import annotations

import argparse
import json
import os
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
    if int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) > 1:
        raise ValueError(
            "Do not rerun all release jobs. Rerun failed jobs to reuse the original "
            "build; if planning failed, rerun CI for the current commit."
        )
    if source != git("rev-parse", "HEAD"):
        raise ValueError("CI source is superseded. Run CI for the current commit.")
    if not all(
        (
            os.environ.get("QUACKFRAME_RELEASES_ENABLED") == "true",
            run["conclusion"] == "success",
            run["event"] == "push",
            run["head_repository"]["full_name"] == repository,
            branch in {"main", "release/next"},
        )
    ):
        output(release="false")
        return
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
    if branch == "main" and pr["head"]["ref"] == "release/next":
        if not pr["head"]["repo"] or pr["head"]["repo"]["full_name"] != repository:
            raise ValueError(
                "Promotion must originate from this repository's release/next."
            )
        flow = "promotion"
    decision = plan(branch, flow=flow)
    if decision is None:
        output(release="false")
        return
    candidate_published(decision, repository)
    destination.write_text(
        json.dumps(asdict(decision), indent=2) + "\n", encoding="utf-8"
    )
    output(
        release="true",
        decision=json.dumps(asdict(decision)),
        tag=decision.tag,
        version=decision.version,
        prerelease=str(decision.prerelease).lower(),
    )


def verify_bundle(bundle: Path, release: Release) -> dict[str, str]:
    hashes = verify(bundle, release.source, release.tag)
    if Release.read(bundle / "release.json") != release:
        raise ValueError("Build release decision conflicts with the planned identity.")
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
            raise ValueError("Selected RC has conflicting candidate identity.")
        if reconcile(hashes, published_hashes(metadata.version)):
            raise ValueError("Selected RC publication on PyPI is incomplete.")


def finalize(release: Release, bundle: Path, repository: str) -> None:
    """Create the GitHub release only after the exact build is present on PyPI."""
    hashes = verify_bundle(bundle, release)
    if reconcile(hashes, published_hashes(release.version)):
        raise ValueError("PyPI publication incomplete; cannot finalize.")
    candidate_published(release, repository)
    tagged = api(f"repos/{repository}/git/ref/tags/{release.tag}", optional=True)
    if tagged is not None and (
        api(f"repos/{repository}/commits/{release.tag}")["sha"] != release.source
    ):
        raise ValueError("Release tag belongs to another source.")
    record = api(f"repos/{repository}/releases/tags/{release.tag}", optional=True)
    if record is not None:
        if tagged is None:
            raise ValueError("GitHub release has no matching source tag.")
        verify_github_identity(record, release)
        with tempfile.TemporaryDirectory(prefix="quackframe-release-") as directory:
            existing = Path(directory)
            download(release.tag, existing)
            if verify_bundle(existing, release) != hashes:
                raise ValueError("GitHub release artifacts differ from this build.")
        return
    # gh creates the tag at this exact commit together with the public release.
    # If only the tag survived a failed request, the identity check above permits retry.
    command(
        "gh",
        "release",
        "create",
        release.tag,
        *[str(path) for path in sorted(bundle.iterdir())],
        "--target",
        release.source,
        "--title",
        release.tag,
        "--notes-file",
        str(bundle / "CHANGELOG.md"),
        *(["--prerelease", "--latest=false"] if release.prerelease else ["--latest"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["plan", "prepare", "stage", "verify", "finalize"]
    )
    parser.add_argument("--decision", type=Path, default=Path("release-plan.json"))
    parser.add_argument("--bundle", type=Path, default=Path("release-bundle"))
    args = parser.parse_args()
    if args.operation == "plan":
        workflow_plan(args.decision)
        return
    # Privileged jobs receive the planner's decision directly through job outputs,
    # independently of every file produced by the candidate build job.
    release = (
        Release(**json.loads(os.environ["PLANNED_RELEASE"]))
        if "PLANNED_RELEASE" in os.environ
        else Release.read(args.decision)
    )
    for name, expected in (("SOURCE", release.source), ("TAG", release.tag)):
        if name in os.environ and os.environ[name] != expected:
            raise ValueError(f"Release decision differs from the workflow {name}.")
    if args.operation == "prepare":
        from scripts.release import prepare

        prepare(release, args.bundle)
        return
    if args.operation in {"stage", "verify"}:
        from scripts.release_artifacts import stage, verify_publication

        hashes = verify_bundle(args.bundle, release)
        if args.operation == "stage":
            stage(args.bundle, hashes, release.version)
        else:
            verify_publication(hashes, release.version)
        return
    finalize(release, args.bundle, os.environ["GITHUB_REPOSITORY"])


if __name__ == "__main__":
    main()
