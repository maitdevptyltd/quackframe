"""Validate release distributions and compare PyPI uploads with the original build."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import time
import zipfile
from email import message_from_bytes
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts.release_identity import package_version


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_distributions(files: list[Path], version: str) -> None:
    """Check the built wheel and sdist against the planned package version."""
    for path in files:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = [
                    n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
                ]
                if len(names) != 1:
                    raise ValueError("Wheel must have one package metadata record.")
                payload = archive.read(names[0])
        else:
            with tarfile.open(path) as archive:
                names = [
                    n
                    for n in archive.getnames()
                    if n.count("/") == 1 and n.endswith("/PKG-INFO")
                ]
                if len(names) != 1:
                    raise ValueError(
                        "Source distribution must have root package metadata."
                    )
                stream = archive.extractfile(names[0])
                if stream is None:
                    raise ValueError("Missing source package metadata.")
                payload = stream.read()
        package = message_from_bytes(payload)
        if package["Name"] != "quackframe" or package["Version"] != version:
            raise ValueError("Distribution identity differs from the release plan.")


def verify(bundle: Path, source: str, tag: str) -> dict[str, str]:
    """Check build identity and compute hashes directly from the distributions."""
    metadata = json.loads((bundle / "release.json").read_text(encoding="utf-8"))
    if metadata["source"] != source or metadata["tag"] != tag:
        raise ValueError("Release assets belong to another source or version.")
    if metadata["version"] != package_version(tag):
        raise ValueError("Release tag and package version identity disagree.")
    files = sorted([*bundle.glob("*.whl"), *bundle.glob("*.tar.gz")])
    if len(files) != 2 or len(list(bundle.glob("*.whl"))) != 1:
        raise ValueError("A release must contain exactly one wheel and one sdist.")
    if {path.name for path in bundle.iterdir()} != {
        *[path.name for path in files],
        "release.json",
        "CHANGELOG.md",
    }:
        raise ValueError("Unexpected artifacts in the release bundle.")
    verify_distributions(files, metadata["version"])
    return {path.name: digest(path) for path in files}


def published_hashes(version: str) -> dict[str, str]:
    try:
        with urlopen(
            f"https://pypi.org/pypi/quackframe/{version}/json", timeout=30
        ) as reply:
            data = json.load(reply)
    except HTTPError as exc:
        if exc.code == 404:
            return {}
        raise
    return {item["filename"]: item["digests"]["sha256"] for item in data["urls"]}


def reconcile(expected: dict[str, str], published: dict[str, str]) -> set[str]:
    """Permit only missing files; existing different bytes stop publication."""
    for name, value in published.items():
        if expected.get(name) != value:
            raise ValueError(f"PyPI already contains conflicting artifact: {name}")
    return expected.keys() - published.keys()


def verify_publication(expected: dict[str, str], version: str) -> None:
    """Allow cached missing files to become visible without retrying uploads."""
    # PyPI can cache missing versions for roughly a minute. Allow three minutes
    # for visibility; an in-flight request retains its existing 30-second timeout.
    deadline = time.monotonic() + 180
    while True:
        missing = reconcile(expected, published_hashes(version))
        if not missing:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(
                f"PyPI publication incomplete after 180 seconds: {sorted(missing)}"
            )
        time.sleep(min(20, remaining))


def stage(bundle: Path, expected: dict[str, str], version: str) -> None:
    """Retry only missing files from this workflow's original build artifact."""
    missing = reconcile(expected, published_hashes(version))
    destination = Path("publish-dist")
    destination.mkdir(exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("Upload staging directory must be empty.")
    for name in missing:
        shutil.copy2(bundle / name, destination / name)
    print(f"{len(missing)} distribution(s) need uploading.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify-local"])
    parser.add_argument("--bundle", type=Path, default=Path("release-bundle"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    verify(args.bundle, args.source, args.tag)


if __name__ == "__main__":
    main()
