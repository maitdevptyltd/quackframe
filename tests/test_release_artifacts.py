"""Publication retries must preserve byte identity, including retained evidence."""

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.release_artifacts import digest, reconcile, seal, verify


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    metadata = b"Name: quackframe\nVersion: 0.1.0\n"
    with zipfile.ZipFile(tmp_path / "quackframe-0.1.0.whl", "w") as wheel:
        wheel.writestr("quackframe-0.1.0.dist-info/METADATA", metadata)
    with tarfile.open(tmp_path / "quackframe-0.1.0.tar.gz", "w:gz") as sdist:
        entry = tarfile.TarInfo("quackframe-0.1.0/PKG-INFO")
        entry.size = len(metadata)
        sdist.addfile(entry, io.BytesIO(metadata))
    (tmp_path / "CHANGELOG.md").write_text("release notes", encoding="utf-8")
    (tmp_path / "release.json").write_text(
        json.dumps({"source": "abc", "tag": "v0.1.0", "version": "0.1.0"}),
        encoding="utf-8",
    )
    seal(tmp_path)
    return tmp_path


def test_retained_artifacts_require_original_source_and_hashes(bundle: Path) -> None:
    expected = verify(bundle, "abc", "v0.1.0")
    assert len(expected) == 2
    with pytest.raises(ValueError, match="another source"):
        verify(bundle, "different", "v0.1.0")
    (bundle / "quackframe-0.1.0.whl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify(bundle, "abc", "v0.1.0")


def test_partial_upload_stages_only_missing_files() -> None:
    expected = {"package.whl": "wheel-hash", "package.tar.gz": "sdist-hash"}
    assert reconcile(expected, {}) == expected.keys()
    assert reconcile(expected, {"package.whl": "wheel-hash"}) == {"package.tar.gz"}
    assert reconcile(expected, expected) == set()
    with pytest.raises(ValueError, match="conflicting"):
        reconcile(expected, {"package.whl": "different-hash"})
    with pytest.raises(ValueError, match="conflicting"):
        reconcile(expected, {"unexpected.whl": "extra"})


def test_missing_distribution_is_not_a_complete_bundle(bundle: Path) -> None:
    (bundle / "quackframe-0.1.0.tar.gz").unlink()
    with pytest.raises(ValueError, match="exactly"):
        seal(bundle)


def test_manifest_cannot_escape_bundle(bundle: Path) -> None:
    (bundle / "SHA256SUMS.json").write_text(
        json.dumps({"../outside.whl": "hash"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checksum"):
        verify(bundle, "abc", "v0.1.0")


def test_distribution_version_must_match_release_plan(bundle: Path) -> None:
    (bundle / "release.json").write_text(
        json.dumps({"version": "0.2.0"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="identity"):
        seal(bundle)


def test_verified_hashes_cannot_hide_conflicting_version(bundle: Path) -> None:
    metadata_path = bundle / "release.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["version"] = "0.2.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    hashes_path = bundle / "SHA256SUMS.json"
    hashes = json.loads(hashes_path.read_text())
    hashes["release.json"] = digest(metadata_path)
    hashes_path.write_text(json.dumps(hashes), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        verify(bundle, "abc", "v0.1.0")
