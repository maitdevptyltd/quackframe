"""The release decision shared by preparation, retention and publication jobs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Flow = Literal["candidate", "promotion", "patch"]


def package_version(tag: str) -> str:
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-rc\.(\d+))?", tag)
    if not match:
        raise ValueError("Invalid release tag.")
    return match[1] + (f"rc{match[2]}" if match[2] else "")


@dataclass(frozen=True)
class Release:
    source: str
    branch: str
    tag: str
    version: str
    prerelease: bool
    flow: Flow
    candidate_tag: str | None = None
    candidate_source: str | None = None

    def __post_init__(self) -> None:
        if self.version != package_version(self.tag):
            raise ValueError("Release tag and package version disagree.")
        if self.prerelease != (self.branch == "release/next") or self.prerelease != (
            "-rc." in self.tag
        ):
            raise ValueError("Release branch and prerelease identity disagree.")
        if self.flow not in {"candidate", "promotion", "patch"} or self.branch not in {
            "main",
            "release/next",
        }:
            raise ValueError("Unknown release flow or branch.")
        if (self.flow == "candidate") != self.prerelease:
            raise ValueError("Release flow and version disagree.")
        if self.flow == "promotion":
            if not self.candidate_tag or not self.candidate_source:
                raise ValueError("Promotion requires a selected candidate and source.")
            if (
                "-rc." not in self.candidate_tag
                or self.candidate_tag.split("-rc.")[0] != self.tag
            ):
                raise ValueError(
                    "Promotion must remove the selected candidate's suffix."
                )
        elif self.candidate_tag or self.candidate_source:
            raise ValueError("Only promotions can select a candidate.")

    @classmethod
    def read(cls, path: Path) -> Release:
        return cls(**json.loads(path.read_text(encoding="utf-8")))
