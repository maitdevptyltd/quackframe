"""Plan and prepare releases without committing, tagging, or publishing.

Semantic Release owns classification, version calculation and note rendering.
Quackframe records bootstrap and promotion constraints in one release decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tomllib
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import cast

from git import Repo
from packaging.version import Version
from semantic_release.changelog.context import make_changelog_context
from semantic_release.changelog.release_history import ReleaseHistory
from semantic_release.cli.changelog_writer import render_default_changelog_file
from semantic_release.cli.config import RawConfig
from semantic_release.commit_parser import CommitParser, ParserOptions
from semantic_release.commit_parser.conventional.options import (
    ConventionalCommitParserOptions,
)
from semantic_release.commit_parser.conventional.parser import ConventionalCommitParser
from semantic_release.commit_parser.token import ParsedCommit, ParseResult
from semantic_release.enums import LevelBump
from semantic_release.hvcs.github import Github
from semantic_release.version.algorithm import next_version
from semantic_release.version.translator import VersionTranslator
from tomlkit import dumps, parse

from scripts.release_identity import Flow, Release


def command(*args: str) -> str:
    """Run an argument vector without shell interpolation."""
    return subprocess.run(
        args, check=True, capture_output=True, text=True
    ).stdout.strip()


def git(*args: str) -> str:
    return command("git", *args)


def release_tags() -> dict[str, Version]:
    return {
        tag: Version(tag[1:])
        for tag in git("tag", "--list").splitlines()
        if re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag)
    }


def configuration() -> tuple[RawConfig, ConventionalCommitParser]:
    with Path("pyproject.toml").open("rb") as stream:
        settings = RawConfig.model_validate(
            tomllib.load(stream)["tool"]["semantic_release"]
        )
    parser = ConventionalCommitParser(
        ConventionalCommitParserOptions(**settings.commit_parser_options)
    )
    return settings, parser


def parsed_changes(
    repo: Repo, parser: ConventionalCommitParser, excluded: list[str]
) -> list[ParsedCommit]:
    changes: list[ParsedCommit] = []
    for sha in git("rev-list", "HEAD", "--not", *excluded).splitlines():
        result = parser.parse(repo.commit(sha))
        changes.extend(
            item
            for item in (result if isinstance(result, list) else [result])
            if isinstance(item, ParsedCommit)
        )
    return changes


def plan(
    branch: str, *, flow: Flow | None = None, candidate_tag: str | None = None
) -> Release | None:
    """Propose a local decision; the workflow must verify remote evidence."""
    if branch not in {"main", "release/next"}:
        raise ValueError("Only main and release/next can publish.")
    if git("branch", "--show-current") != branch:
        raise ValueError("Checkout must be on the requested release branch.")
    if flow == "candidate" and branch != "release/next":
        raise ValueError("Candidate flow requires release/next.")
    if branch == "release/next" and (flow in {"promotion", "patch"} or candidate_tag):
        raise ValueError("Stable flows require main.")

    with Repo(".") as repo:
        source = repo.head.commit.hexsha
        tags = release_tags()
        reachable = set(git("tag", "--merged", "HEAD").splitlines())
        stable = {tag: v for tag, v in tags.items() if not v.is_prerelease}
        if stable and max(stable, key=lambda tag: stable[tag]) not in reachable:
            raise ValueError("Synchronize the latest stable release before releasing.")
        if branch == "release/next" and any(
            repo.commit(t).hexsha == source for t in stable
        ):
            return None
        existing = [
            tag
            for tag, v in tags.items()
            if repo.commit(tag).hexsha == source
            and v.is_prerelease == (branch == "release/next")
        ]
        if len(existing) > 1:
            raise ValueError("Multiple release identities at this commit.")

        # A retry's baseline excludes its own stable tag.
        prior_stable = {tag: v for tag, v in stable.items() if tag not in existing}
        excluded = sorted(
            reachable
            & (tags.keys() if branch == "release/next" else prior_stable.keys())
        )
        settings, parser = configuration()
        changes = parsed_changes(repo, parser, excluded)
        if not existing and not any(c.bump > LevelBump.NO_RELEASE for c in changes):
            if flow == "promotion":
                raise ValueError("Promotion has no qualifying candidate work.")
            return None
        translator = VersionTranslator(tag_format=settings.tag_format)
        calculated = str(
            next_version(
                repo,
                translator,
                cast(CommitParser[ParseResult, ParserOptions], parser),
                settings.allow_zero_version,
                settings.major_on_zero,
                prerelease=branch == "release/next",
            )
        )
        if existing:
            calculated = existing[0][1:]
        elif not stable:
            if any(
                v.release != (0, 1, 0) or tag not in reachable
                for tag, v in tags.items()
            ):
                raise ValueError(
                    "Initial candidate history conflicts with the 0.1.0 bootstrap."
                )
            revision = max((v.pre[1] for v in tags.values() if v.pre), default=0) + 1
            calculated = f"0.1.0-rc.{revision}" if branch == "release/next" else "0.1.0"
        version = Version(calculated)
        tag = f"v{calculated}"
        if not existing and version in tags.values():
            raise ValueError(
                "Calculated release version already belongs to another commit."
            )

        selected: str | None = None
        selected_source: str | None = None
        selected_flow: Flow = "candidate"
        if branch == "main":
            covered: set[str] = set()
            for stable_tag in prior_stable:
                covered.update(git("tag", "--merged", stable_tag).splitlines())
            candidates = [
                t
                for t, v in tags.items()
                if v.is_prerelease
                and t in reachable - covered
                and v.release == version.release
            ]
            # A patch-sized RC is still a promotion. Hosted execution also checks
            # the merged PR's source branch and its explicitly selected candidate.
            promotion = (
                flow == "promotion" or candidate_tag is not None or bool(candidates)
            )
            if promotion:
                if flow == "patch":
                    raise ValueError(
                        "Candidate ancestry conflicts with direct-patch provenance."
                    )
                if candidate_tag is not None and candidate_tag not in candidates:
                    raise ValueError(
                        "Selected published RC is absent, unreachable "
                        "or targets another version."
                    )
                if not candidates:
                    raise ValueError("Promotion requires a published RC.")
                selected = candidate_tag or max(candidates, key=lambda t: tags[t])
                selected_source = repo.commit(selected).hexsha
                if repo.commit(selected).tree.hexsha != repo.head.commit.tree.hexsha:
                    raise ValueError(
                        "Promotion differs from the tested RC; cut a new RC."
                    )
                selected_flow = "promotion"
            else:
                previous = max(prior_stable.values(), default=Version("0.0.0"))
                is_patch = bool(prior_stable) and version.release == (
                    previous.major,
                    previous.minor,
                    previous.micro + 1,
                )
                if not is_patch:
                    raise ValueError(
                        "Feature releases require a published RC promotion."
                    )
                selected_flow = "patch"
        return Release(
            source,
            branch,
            tag,
            str(version),
            version.is_prerelease,
            selected_flow,
            selected,
            selected_source,
        )


def prepare(release: Release, destination: Path) -> None:
    """Revalidate the decision, then stamp and render that exact release identity."""
    if git("rev-parse", "HEAD") != release.source:
        raise ValueError("Release source changed after planning.")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Preparation requires an unchanged source checkout.")
    if release.tag in release_tags():
        raise ValueError(
            "Reserved releases must reuse retained artifacts; do not rebuild."
        )
    if (
        plan(release.branch, flow=release.flow, candidate_tag=release.candidate_tag)
        != release
    ):
        raise ValueError("Release decision changed after planning.")
    settings, parser = configuration()
    with Repo(".") as repo:
        stable = [tag for tag, v in release_tags().items() if not v.is_prerelease]
        elements: dict[str, list[ParseResult]] = defaultdict(list)
        # Describe the delivery since stable, including all RC work at promotion.
        # Traversing tags alone would leave the promotion's own notes empty.
        for change in parsed_changes(repo, parser, stable):
            if change.include_in_changelog:
                elements[change.type].append(change)
        history = ReleaseHistory(elements, {}).release(
            VersionTranslator().from_string(release.tag[1:]),
            repo.head.commit.author,
            repo.head.commit.committer,
            repo.head.commit.committed_datetime,
        )
        context = make_changelog_context(
            Github(git("remote", "get-url", "origin")),
            history,
            settings.changelog.mode,
            Path("CHANGELOG.md"),
            settings.changelog.insertion_flag,
            settings.changelog.default_templates.mask_initial_release,
        )
        notes = (
            render_default_changelog_file(
                settings.changelog.default_templates.output_format,
                context,
                "conventional",
            )
            + "\n"
        )
    project_file = Path("pyproject.toml")
    document = parse(project_file.read_text(encoding="utf-8"))
    document["project"]["version"] = release.version  # type: ignore[index]
    project_file.write_text(dumps(document), encoding="utf-8")
    Path("CHANGELOG.md").write_text(notes, encoding="utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "release.json").write_text(
        json.dumps(asdict(release), indent=2) + "\n", encoding="utf-8"
    )
    (destination / "CHANGELOG.md").write_text(notes, encoding="utf-8")


def write_outputs(values: dict[str, str]) -> None:
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", choices=["main", "release/next"])
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("release-bundle"))
    args = parser.parse_args()
    release = plan(args.branch)
    outputs = {"release": str(release is not None).lower()}
    if release:
        outputs.update(
            tag=release.tag,
            version=release.version,
            prerelease=str(release.prerelease).lower(),
        )
        print(json.dumps(asdict(release), indent=2))
        if args.prepare:
            prepare(release, args.output)
    else:
        print("No release-worthy changes.")
    write_outputs(outputs)


if __name__ == "__main__":
    main()
