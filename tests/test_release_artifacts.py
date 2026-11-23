"""Publication retries compare the original build bytes with PyPI."""

import io
import json
import tarfile
import zipfile
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from scripts import release_artifacts
from scripts.release_artifacts import reconcile, verify


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
    return tmp_path


def test_bundle_requires_original_source(bundle: Path) -> None:
    assert len(verify(bundle, "abc", "v0.1.0")) == 2
    with pytest.raises(ValueError, match="another source"):
        verify(bundle, "different", "v0.1.0")


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
        verify(bundle, "abc", "v0.1.0")


def test_unexpected_file_is_rejected(bundle: Path) -> None:
    (bundle / "unexpected.whl").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="exactly"):
        verify(bundle, "abc", "v0.1.0")


def test_distribution_version_must_match_release_plan(bundle: Path) -> None:
    metadata = json.loads((bundle / "release.json").read_text())
    metadata.update(tag="v0.2.0", version="0.2.0")
    (bundle / "release.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="identity"):
        verify(bundle, "abc", "v0.2.0")


@pytest.mark.parametrize(
    "outcome",
    ["delayed", "timeout", "hash", "extra", "http", "network", "malformed"],
)
def test_pypi_verification_polling(
    bundle: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    expected = verify(bundle, "abc", "v0.1.0")
    elapsed = 0.0
    requests: list[float] = []

    def sleep(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    def urlopen(url: str, timeout: int) -> io.StringIO:
        assert url == "https://pypi.org/pypi/quackframe/0.1.0/json"
        assert timeout == 30
        requests.append(elapsed)
        if outcome == "timeout" or elapsed < 80:
            raise HTTPError(url, 404, "Not Found", Message(), None)
        if outcome == "http":
            raise HTTPError(url, 503, "Unavailable", Message(), None)
        if outcome == "network":
            raise URLError("offline")
        if outcome == "malformed":
            return io.StringIO("invalid JSON")
        published = dict(expected)
        if outcome == "hash":
            published[next(iter(expected))] = "different-hash"
        if outcome == "extra":
            published["unexpected.whl"] = "extra-hash"
        if outcome == "delayed" and elapsed == 80:
            published.pop(next(iter(expected)))
        return io.StringIO(
            json.dumps(
                {
                    "urls": [
                        {"filename": name, "digests": {"sha256": value}}
                        for name, value in published.items()
                    ]
                }
            )
        )

    monkeypatch.setattr(release_artifacts.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(release_artifacts.time, "sleep", sleep)
    monkeypatch.setattr(release_artifacts, "urlopen", urlopen)
    if outcome == "delayed":
        release_artifacts.verify_publication(expected, "0.1.0")
        assert requests == [0, 20, 40, 60, 80, 100]
        return

    error, message = {
        "timeout": (ValueError, "incomplete after 180 seconds"),
        "hash": (ValueError, "conflicting artifact"),
        "extra": (ValueError, "conflicting artifact"),
        "http": (HTTPError, "503"),
        "network": (URLError, "offline"),
        "malformed": (json.JSONDecodeError, "Expecting value"),
    }[outcome]
    with pytest.raises(error, match=message) as failure:
        release_artifacts.verify_publication(expected, "0.1.0")
    if outcome == "timeout":
        assert requests == list(range(0, 181, 20))
        assert all(name in str(failure.value) for name in expected)
    else:
        assert requests == [0, 20, 40, 60, 80]
