"""Test-only metadata tracing around real Paramiko calls, never packet payloads."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from paramiko.sftp import CMD_NAMES


class PacketTrace:
    """Flush metadata before a child can be killed; never lock a network call."""

    def __init__(self, path: Path, role: str) -> None:
        self.path = path
        self.role = role
        self.stream = path.open("w", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()
        self.local = threading.local()

    def emit(self, event: str, client: Any, **fields: Any) -> None:
        channel = getattr(client, "sock", None)
        record = {
            "time_ns": time.monotonic_ns(),
            "pid": os.getpid(),
            "thread": threading.get_ident(),
            "native_thread": threading.get_native_id(),
            "role": self.role,
            "client": id(client),
            "channel": getattr(channel, "chanid", None),
            "event": event,
            "waitfor": getattr(self.local, "waitfor", None),
            "operation": getattr(self.local, "operation", None),
            **fields,
        }
        # Only protect one log write. Holding this across a request would mask
        # the very race this harness is intended to observe.
        with self.lock:
            self.stream.write(json.dumps(record) + "\n")

    def close(self) -> None:
        self.stream.close()

    @contextmanager
    def instrument(self, client_type: type[Any]) -> Generator[None]:
        """Wrap library hooks, delegating every call to its original method."""
        trace = self
        originals: dict[str, Any] = {}
        own_attributes: set[str] = set()

        def wrap(name: str) -> None:
            original = getattr(client_type, name)
            originals[name] = original
            if name in client_type.__dict__:
                own_attributes.add(name)

            def observed(client: Any, *args: Any, **kwargs: Any) -> Any:
                old_wait = getattr(trace.local, "waitfor", None)
                old_operation = getattr(trace.local, "operation", None)
                fields: dict[str, Any] = {}
                if name == "_request":
                    trace.local.operation = CMD_NAMES.get(args[0], str(args[0]))
                elif name == "_read_response":
                    trace.local.waitfor = args[0] if args else kwargs.get("waitfor")
                elif name == "_read_all":
                    fields["bytes_requested"] = args[0]
                elif name == "_send_packet":
                    command, message = args
                    data = message.asbytes()
                    fields = packet_fields(command, data)
                trace.emit(name + ".begin", client, **fields)
                try:
                    result = original(client, *args, **kwargs)
                    if name == "_read_packet":
                        fields = packet_fields(*result)
                    elif name == "_read_all":
                        fields["bytes_returned"] = len(result)
                    trace.emit(name + ".end", client, **fields)
                    return result
                except BaseException as error:
                    # Exception text can contain paths or credentials; type suffices.
                    trace.emit(name + ".error", client, error_type=type(error).__name__)
                    raise
                finally:
                    trace.local.waitfor = old_wait
                    trace.local.operation = old_operation

            setattr(client_type, name, observed)

        try:
            for name in ("_send_packet", "_read_packet", "_read_all"):
                wrap(name)
            if hasattr(client_type, "_request"):
                wrap("_request")
                wrap("_read_response")
            yield
        finally:
            for name, original in originals.items():
                if name in own_attributes:
                    setattr(client_type, name, original)
                else:
                    delattr(client_type, name)


def packet_fields(command: int, data: bytes) -> dict[str, Any]:
    """Read only framing metadata; INIT/VERSION contain a version, not an ID."""
    return {
        "packet_type": command,
        "packet_name": CMD_NAMES.get(command, str(command)),
        "request_id": int.from_bytes(data[:4], "big")
        if command not in (1, 2) and len(data) >= 4
        else None,
        "packet_bytes": len(data) + 1,
    }


def summarize_trace(root: Path) -> dict[str, Any]:
    """Correlate the single-connection probes without assuming a race outcome."""

    def read(name: str) -> list[dict[str, Any]]:
        path = root / name
        if not path.exists():
            return []
        # Forced process termination may leave a partial final line.
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    client = read("client-trace.jsonl")
    server = read("server-trace.jsonl")
    sent = {
        r["request_id"]
        for r in client
        if r["event"] == "_send_packet.end" and r["request_id"] is not None
    }
    received = {
        r["request_id"]
        for r in server
        if r["event"] == "_read_packet.end" and r["request_id"] is not None
    }
    replied = {
        r["request_id"]
        for r in server
        if r["event"] == "_send_packet.end" and r["request_id"] is not None
    }
    pending: dict[tuple[int, int], dict[str, Any]] = {}
    overlaps: list[dict[str, Any]] = []
    readers: dict[int, set[int]] = {}
    for record in client:
        event, thread = record["event"], record["thread"]
        if event == "_read_response.begin" and record["waitfor"] is not None:
            pending[thread, record["waitfor"]] = record
        elif (
            event in {"_read_response.end", "_read_response.error"}
            and record["waitfor"] is not None
        ):
            pending.pop((thread, record["waitfor"]), None)
        if event == "_read_packet.begin":
            active = readers.setdefault(record["client"], set())
            if active:
                overlaps.append(
                    {
                        "time_ns": record["time_ns"],
                        "thread": thread,
                        "other_threads": sorted(active),
                    }
                )
            active.add(thread)
        elif event in {"_read_packet.end", "_read_packet.error"}:
            readers.setdefault(record["client"], set()).discard(thread)
    mismatches = [
        r
        for r in client
        if r["event"] == "_read_packet.end"
        and r["waitfor"] is not None
        and r["request_id"] is not None
        and r["waitfor"] != r["request_id"]
    ]
    server_packets = {
        (r["request_id"], r["packet_type"], r["packet_bytes"])
        for r in server
        if r["event"] == "_send_packet.end"
    }
    sent_requests = {
        r["request_id"]: r for r in client if r["event"] == "_send_packet.end"
    }
    waited_ids = {r["waitfor"] for r in client if r["event"] == "_read_response.begin"}
    async_close_replies: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    for reply in mismatches:
        request = sent_requests.get(reply["request_id"], {})
        signature = (reply["request_id"], reply["packet_type"], reply["packet_bytes"])
        # Paramiko file destructors queue CLOSE without waiting. A later caller
        # may safely drain that STATUS, but never another synchronous reply.
        if (
            request.get("packet_name") == "close"
            and request.get("operation") is None
            and reply["request_id"] not in waited_ids
            and reply["packet_name"] == "status"
            and signature in server_packets
        ):
            async_close_replies.append(reply)
        else:
            unexplained.append(reply)
    stranded: list[dict[str, Any]] = []
    for response in mismatches:
        signature = (
            response["request_id"],
            response["packet_type"],
            response["packet_bytes"],
        )
        for waiter in pending.values():
            if (
                waiter["waitfor"] == response["request_id"]
                and waiter["thread"] != response["thread"]
                and signature in server_packets
            ):
                stranded.append(
                    {
                        "request_id": response["request_id"],
                        "waiting_thread": waiter["thread"],
                        "consuming_thread": response["thread"],
                        "consumer_waitfor": response["waitfor"],
                        "packet_name": response["packet_name"],
                        "time_ns": response["time_ns"],
                    }
                )
    summary = {
        "client_events": len(client),
        "server_events": len(server),
        "client_requests_sent": len(sent),
        "server_requests_received": len(received),
        "server_responses_sent": len(replied),
        "sent_not_seen_by_server": sorted(sent - received),
        "received_without_server_response": sorted(received - replied),
        "overlapping_packet_reads": overlaps,
        "response_id_different_from_waiter": mismatches,
        "responses_consumed_by_other_pending_waiters": stranded,
        "async_close_replies": async_close_replies,
        "unexplained_response_mismatches": unexplained,
        "pending_waiters": [
            {**r, "server_sent_response": r["waitfor"] in replied}
            for r in pending.values()
        ],
        "unusually_large_read_requests": [
            r
            for r in client
            if r["event"] == "_read_all.begin" and r["bytes_requested"] > 1024 * 1024
        ],
        "note": "Pipelined reply mismatches and overlaps alone do not prove loss. "
        "Server send completion means bytes handed to SSH, not client consumption.",
    }
    (root / "trace-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
