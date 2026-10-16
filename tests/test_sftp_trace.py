"""Check diagnostic correlation without replacing any SFTP transport behavior."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("paramiko")

from sftp_trace import packet_fields, summarize_trace


def test_packet_metadata_excludes_payload_and_handshake_version() -> None:
    payload = (7).to_bytes(4, "big") + b"private-data-not-to-log"
    metadata = packet_fields(101, payload)
    assert metadata["request_id"] == 7
    assert "private-data" not in json.dumps(metadata)
    assert packet_fields(1, payload)["request_id"] is None
    assert packet_fields(2, payload)["request_id"] is None


@pytest.mark.parametrize("complete_waiter", [False, True])
def test_trace_distinguishes_stranded_waiters_from_drained_replies(
    tmp_path: Path,
    complete_waiter: bool,
) -> None:
    def event(kind: str, thread: int, waitfor: int, **extra: Any) -> dict[str, Any]:
        return {
            "event": kind,
            "thread": thread,
            "waitfor": waitfor,
            "client": 1,
            "time_ns": 1,
            **extra,
        }

    packet = {
        "request_id": 10,
        "packet_type": 102,
        "packet_name": "handle",
        "packet_bytes": 12,
    }
    client = [
        event("_read_response.begin", 1, 6),
        event("_read_response.begin", 2, 10),
        event("_read_packet.end", 1, 6, **packet),
    ]
    if complete_waiter:
        client.append(event("_read_response.end", 2, 10))
    server = [event("_send_packet.end", 3, 0, **packet)]
    for name, records in [("client", client), ("server", server)]:
        (tmp_path / f"{name}-trace.jsonl").write_text(
            "\n".join(json.dumps(record) for record in records), encoding="utf-8"
        )
    result = summarize_trace(tmp_path)
    assert len(result["response_id_different_from_waiter"]) == 1
    stranded = result["responses_consumed_by_other_pending_waiters"]
    assert len(stranded) == (0 if complete_waiter else 1)
    if stranded:
        assert stranded[0]["waiting_thread"] == 2
        assert stranded[0]["consuming_thread"] == 1
        assert stranded[0]["request_id"] == 10


@pytest.mark.parametrize("has_waiter", [False, True])
def test_only_unawaited_close_status_is_classified_as_benign(
    tmp_path: Path,
    has_waiter: bool,
) -> None:
    packet = {
        "request_id": 10,
        "packet_type": 101,
        "packet_name": "status",
        "packet_bytes": 24,
    }
    client = [
        {
            "event": "_send_packet.end",
            "request_id": 10,
            "packet_name": "close",
            "operation": None,
            "thread": 1,
            "client": 1,
            "waitfor": None,
        },
        {
            "event": "_read_packet.end",
            "thread": 2,
            "client": 1,
            "waitfor": 11,
            "time_ns": 1,
            **packet,
        },
    ]
    if has_waiter:
        client.insert(
            1,
            {"event": "_read_response.begin", "thread": 1, "client": 1, "waitfor": 10},
        )
    server = [{"event": "_send_packet.end", **packet}]
    for name, records in [("client", client), ("server", server)]:
        (tmp_path / f"{name}-trace.jsonl").write_text(
            "\n".join(json.dumps(record) for record in records), encoding="utf-8"
        )
    result = summarize_trace(tmp_path)
    assert len(result["async_close_replies"]) == (0 if has_waiter else 1)
    assert len(result["unexplained_response_mismatches"]) == (1 if has_waiter else 0)
