"""Keep expected upstream races distinct from protected-client regressions."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")

from test_sftp_integration import read_probe_result


@pytest.mark.parametrize("layer", ["paramiko", "fsspec", "duckdb"])
@pytest.mark.parametrize("threads", [1, 4])
@pytest.mark.parametrize("turn_taking", [False, True])
@pytest.mark.parametrize("case", ["multi", "mixed"])
def test_packet_race_is_expected_only_in_unprotected_controls(
    tmp_path: Path, layer: str, threads: int, turn_taking: bool, case: str
) -> None:
    (tmp_path / "error.json").write_text(
        json.dumps(
            {"type": "paramiko.sftp.SFTPError", "message": "Garbage packet received"}
        ),
        encoding="utf-8",
    )
    expected = (
        pytest.xfail.Exception
        if layer in {"paramiko", "fsspec"}
        and threads == 4
        and not turn_taking
        and case == "multi"
        else AssertionError
    )
    with pytest.raises(expected):
        read_probe_result(
            tmp_path,
            1,
            "child traceback",
            case=case,
            threads=threads,
            layer=layer,
            turn_taking=turn_taking,
        )


@pytest.mark.parametrize(
    "error",
    [
        None,
        {"type": "builtins.RuntimeError", "message": "Garbage packet received"},
        {"type": "paramiko.sftp.SFTPError", "message": "Unexpected response"},
    ],
)
def test_unrelated_child_failures_remain_fatal(
    tmp_path: Path, error: dict[str, str] | None
) -> None:
    if error is not None:
        (tmp_path / "error.json").write_text(json.dumps(error), encoding="utf-8")
    # A matching phrase in a traceback alone must never suppress a failure.
    with pytest.raises(AssertionError, match="Garbage packet received"):
        read_probe_result(
            tmp_path,
            1,
            "Garbage packet received",
            case="multi",
            threads=4,
            layer="fsspec",
            turn_taking=False,
        )


def test_successful_control_still_returns_rows(tmp_path: Path) -> None:
    result = {"rows": [["sftp:///example.csv", 3]]}
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    assert (
        read_probe_result(
            tmp_path, 0, "", case="multi", threads=4, layer="fsspec", turn_taking=False
        )
        == result
    )
