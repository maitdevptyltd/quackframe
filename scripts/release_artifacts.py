"""Seal release artifacts and reconcile PyPI uploads by exact file identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import zipfile
from email import message_from_bytes
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts.release_identity import package_version


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_distributions(files: list[Path], version: str) -> None:
    """Inspect package metadata even when the retained hashes match."""
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


def seal(bundle: Path) -> None:
    files = sorted([*bundle.glob("*.whl"), *bundle.glob("*.tar.gz")])
    if len(files) != 2 or len(list(bundle.glob("*.whl"))) != 1:
        raise ValueError("A release must contain exactly one wheel and one sdist.")
    metadata = json.loads((bundle / "release.json").read_text(encoding="utf-8"))
    verify_distributions(files, metadata["version"])
    files.extend([bundle / "release.json", bundle / "CHANGELOG.md"])
    hashes = {path.name: digest(path) for path in files}
    (bundle / "SHA256SUMS.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
    )


def verify(bundle: Path, source: str, tag: str) -> dict[str, str]:
    hashes: dict[str, str] = json.loads(
        (bundle / "SHA256SUMS.json").read_text(encoding="utf-8")
    )
    for name, expected in hashes.items():
        if Path(name).name != name or digest(bundle / name) != expected:
            raise ValueError(f"Release artifact checksum mismatch: {name}")
    if not {"release.json", "CHANGELOG.md"} <= hashes.keys():
        raise ValueError("Missing sealed release evidence.")
    metadata = json.loads((bundle / "release.json").read_text(encoding="utf-8"))
    if metadata["source"] != source or metadata["tag"] != tag:
        raise ValueError("Release assets belong to another source or version.")
    if metadata["version"] != package_version(tag):
        raise ValueError("Release tag and package version identity disagree.")
    distributions = {
        name: value
        for name, value in hashes.items()
        if name.endswith((".whl", ".tar.gz"))
    }
    if len(distributions) != 2 or sum(n.endswith(".whl") for n in distributions) != 1:
        raise ValueError("Missing sealed distributions.")
    if set(hashes) != {*distributions, "release.json", "CHANGELOG.md"} or {
        path.name for path in bundle.iterdir()
    } != {*hashes, "SHA256SUMS.json"}:
        raise ValueError("Unexpected artifacts outside the sealed release bundle.")
    verify_distributions([bundle / name for name in distributions], metadata["version"])
    return distributions


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["seal", "stage", "verify", "verify-local"]
    )
    parser.add_argument("--bundle", type=Path, default=Path("release-bundle"))
    parser.add_argument("--source", default="")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    if args.operation == "seal":
        seal(args.bundle)
        return
    expected = verify(args.bundle, args.source, args.tag)
    if args.operation == "verify-local":
        return
    metadata = json.loads((args.bundle / "release.json").read_text(encoding="utf-8"))
    missing = reconcile(expected, published_hashes(metadata["version"]))
    if args.operation == "verify":
        if missing:
            raise ValueError(f"PyPI publication incomplete: {sorted(missing)}")
        return
    destination = Path("publish-dist")
    destination.mkdir(exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("Upload staging directory must be empty.")
    for name in missing:
        shutil.copy2(args.bundle / name, destination / name)
    print(f"{len(missing)} distribution(s) need uploading.")


if __name__ == "__main__":
    main()
