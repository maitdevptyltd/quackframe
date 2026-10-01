"""Real SFTP/SQL regressions, isolated from Prefect and bounded by process timeouts.

Run with: poetry run pytest tests/test_sftp_integration.py -v
Timeout traces and child output are retained in each pytest temporary directory.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from threading import Event, Thread, current_thread
from typing import Any, BinaryIO

import pytest

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")

from paramiko import (
    RSAKey,
    ServerInterface,
    SFTPAttributes,
    SFTPHandle,
    SFTPServer,
    SFTPServerInterface,
    Transport,
)
from paramiko.common import AUTH_FAILED, AUTH_SUCCESSFUL, OPEN_SUCCEEDED
from sftp_trace import PacketTrace, summarize_trace

FILE_COUNT = 26
BASE_ROWS = 8192
REMOTE = "/from_test/trips"
URL = f"temporary-local-key://127.0.0.1{REMOTE}"
PATTERN = f"{URL}/daily_trips-2026_09_*.csv"


class LoopbackServer:
    """Serve a temporary permission-controlled tree and track accepted sockets."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.trace_resources = ExitStack()
        self.handler = SFTPServer
        self.stop = Event()
        self.stall_reads = False
        self.writable = False
        self.transports: list[Transport] = []
        self.errors: list[Exception] = []
        self.subsystems: list[Thread] = []
        self.opened_paths: list[str] = []
        self.authentication_attempts = 0
        self.handles: list[SFTPHandle] = []
        self.host_key = RSAKey.generate(2048)
        self.user_key = RSAKey.generate(2048)
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        assert self.port != 22
        self.thread = Thread(target=self.serve, daemon=True)

    def enable_trace(self) -> None:
        # Give this server its own instrumented class; untraced fixtures keep
        # the exact standard implementation and no global server hooks change.
        class ObservedServer(SFTPServer):
            pass

        trace = PacketTrace(self.root.parent / "server-trace.jsonl", "server")
        self.trace_resources.callback(trace.close)
        self.trace_resources.enter_context(trace.instrument(ObservedServer))
        self.handler = ObservedServer

    def serve(self) -> None:
        owner = self

        class Authentication(ServerInterface):
            def check_auth_publickey(self, username: str, key: Any) -> int:
                owner.authentication_attempts += 1
                return (
                    AUTH_SUCCESSFUL
                    if username == "reader" and key == owner.user_key
                    else AUTH_FAILED
                )

            def check_channel_request(self, kind: str, chanid: int) -> int:
                return OPEN_SUCCEEDED if kind == "session" else 1

        class ReadHandle(SFTPHandle):
            readfile: BinaryIO
            writefile: BinaryIO

            def read(self, offset: int, length: int) -> bytes | int:
                if owner.stall_reads:
                    owner.stop.wait()
                return super().read(offset, length)

        class Files(SFTPServerInterface):
            def posix_rename(self, oldpath: str, newpath: str) -> int:
                if not owner.writable:
                    return 3
                try:
                    self.target(oldpath).replace(self.target(newpath))
                    return 0
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def session_started(self) -> None:
                owner.subsystems.append(current_thread())

            def target(self, path: str) -> Path:
                target = (owner.root / path.lstrip("/")).resolve()
                if not target.is_relative_to(owner.root.resolve()):
                    raise PermissionError("Outside temporary SFTP root")
                return target

            def list_folder(self, path: str) -> list[SFTPAttributes] | int:
                try:
                    return [
                        SFTPAttributes.from_stat(child.stat(), child.name)
                        for child in self.target(path).iterdir()
                    ]
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def stat(self, path: str) -> SFTPAttributes | int:
                try:
                    return SFTPAttributes.from_stat(self.target(path).stat())
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def mkdir(self, path: str, attr: Any) -> int:
                if not owner.writable:
                    return 3
                try:
                    self.target(path).mkdir()
                    return 0
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def remove(self, path: str) -> int:
                if not owner.writable:
                    return 3
                try:
                    self.target(path).unlink()
                    return 0
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def rmdir(self, path: str) -> int:
                if not owner.writable:
                    return 3
                try:
                    self.target(path).rmdir()
                    return 0
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

            def open(self, path: str, flags: int, attr: Any) -> SFTPHandle | int:
                writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
                if writing and not owner.writable:
                    return 3  # SFTP_PERMISSION_DENIED
                try:
                    handle = ReadHandle(flags)
                    if writing:
                        handle.writefile = os.fdopen(
                            os.open(
                                self.target(path), flags | getattr(os, "O_BINARY", 0)
                            ),
                            "wb",
                        )
                    else:
                        handle.readfile = self.target(path).open("rb")
                    owner.handles.append(handle)
                    owner.opened_paths.append(path)
                    return handle
                except OSError as error:
                    return SFTPServer.convert_errno(error.errno or 13)

        while not self.stop.is_set():
            try:
                client, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                if self.stop.is_set():
                    break
                raise
            try:
                transport = Transport(client)
                self.transports.append(transport)
                transport.add_server_key(self.host_key)
                transport.set_subsystem_handler("sftp", self.handler, Files)
                transport.start_server(server=Authentication())
            except EOFError:
                # A rejected host key can close the socket before start_server
                # returns. This is an expected unauthenticated disconnect.
                client.close()
            except Exception as error:
                self.errors.append(error)
                client.close()

    def wait_disconnected(self) -> None:
        deadline = time.monotonic() + 5
        while (
            any(t.is_active() for t in self.transports) and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert all(not t.is_active() for t in self.transports)

    def close(self) -> None:
        self.stop.set()
        self.listener.close()
        for transport in self.transports:
            transport.close()
        self.thread.join(timeout=5)
        for transport in self.transports:
            transport.join(timeout=5)
        for subsystem in self.subsystems:
            subsystem.join(timeout=5)
        for handle in self.handles:
            handle.close()
        self.trace_resources.close()
        assert not self.thread.is_alive()
        assert all(not t.is_alive() for t in self.transports)
        assert all(not subsystem.is_alive() for subsystem in self.subsystems)
        assert not self.errors


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LoopbackServer]:
    remote = tmp_path / "remote"
    directory = remote / REMOTE.lstrip("/")
    directory.mkdir(parents=True)
    for day in range(1, FILE_COUNT + 1):
        # Over a megabyte per file, distinct counts, and differing headers ensure
        # the wildcard exercises real reads and union_by_name schema discovery.
        header = "trip_id,payload,optional\n" if day % 2 else "payload,trip_id\n"
        row = f"123,{'x' * 128},yes\n" if day % 2 else f"{'x' * 128},123\n"
        (directory / f"daily_trips-2026_09_{day:02}.csv").write_text(
            header + row * (BASE_ROWS + day), encoding="utf-8"
        )
    (directory / "ignore.txt").write_text("not a CSV")
    local = LoopbackServer(remote)
    local.user_key.write_private_key_file(str(tmp_path / "client_key"))
    local.thread.start()
    try:
        yield local
    finally:
        try:
            local.close()
        finally:
            # Remove credentials even when teardown or an assertion fails.
            (tmp_path / "client_key").unlink(missing_ok=True)


def run_probe(
    tmp_path: Path,
    server: LoopbackServer,
    case: str,
    threads: int,
    *,
    timeout: float = 60,
    layer: str = "duckdb",
    trace: bool = False,
    turn_taking: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    """Run the direct runtime in a disposable process; always reap it."""
    if trace:
        server.enable_trace()
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "port": server.port,
                "case": case,
                "layer": layer,
                "trace": trace,
                "turn_taking": turn_taking,
                "threads": threads,
                "dump_after": timeout * 0.7,
            }
        )
    )
    (tmp_path / "register.sql").write_text(
        f"SET threads = {threads};\n"
        "SELECT quackframe.register_filesystem('loopback', 'temporary-local-key', "
        "'sftp', overrides := MAP {'scope': 'sftp://127.0.0.1'});\n"
    )
    if case == "glob":
        query = f"SELECT file FROM glob('{PATTERN}') ORDER BY file"
    else:
        path = (
            f"{URL}/daily_trips-2026_09_01.csv"
            if case in {"single", "failure"}
            else PATTERN
        )
        query = (
            "SELECT filename, count(*) AS row_count FROM read_csv("
            f"'{path}', header = true, all_varchar = true, "
            "union_by_name = true, filename = true) GROUP BY filename ORDER BY filename"
        )
    # Execute the reported SELECT unchanged first. Repeat it into a local table
    # because run() deliberately does not expose query rows to its caller.
    sql = f"{query};\nCREATE TABLE result AS {query};\n"
    if case == "failure":
        sql += f"SELECT * FROM read_csv('{URL}/missing.csv');\n"
        sql += "CREATE TABLE must_not_run AS SELECT 1;\n"
    (tmp_path / "probe.sql").write_text(sql)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    # Do not inherit consumer runtime settings or access a Prefect endpoint.
    environment = {
        key: value
        for key, value in environment.items()
        if not key.startswith(("PREFECT_", "QUACKFRAME_"))
    }
    environment["SSH_AUTH_SOCK"] = ""
    environment["PYTHONUNBUFFERED"] = "1"
    log_path = tmp_path / "child.log"
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("sftp_probe.py")),
                str(tmp_path),
            ],
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
    server.wait_disconnected()
    (tmp_path / "parent.json").write_text(
        json.dumps(
            {
                "case": case,
                "threads": threads,
                "timed_out": timed_out,
                "turn_taking": turn_taking,
                "layer": layer,
                "trace": trace,
                "returncode": process.returncode,
                "port": server.port,
                "connections": len(server.transports),
                "opened_paths": server.opened_paths,
                "active_after_process_exit": sum(
                    t.is_active() for t in server.transports
                ),
            }
        ),
        encoding="utf-8",
    )
    if trace:
        summarize_trace(tmp_path)
    output = log_path.read_text(encoding="utf-8")
    print(f"{case}, threads={threads}, timeout={timed_out}, log={log_path}\n{output}")
    if timed_out:
        return None, output
    assert process.returncode == 0, output
    return json.loads((tmp_path / "result.json").read_text()), output


def expected_counts(
    single: bool = False, port: int | None = None
) -> list[list[object]]:
    prefix = "sftp://" if port is None else f"temporary-local-key://127.0.0.1:{port}"
    return [
        [f"{prefix}{REMOTE}/daily_trips-2026_09_{day:02}.csv", BASE_ROWS + day]
        for day in range(1, (1 if single else FILE_COUNT) + 1)
    ]


def test_discovery_independently(tmp_path: Path, server: LoopbackServer) -> None:
    result, output = run_probe(tmp_path, server, "glob", 4)
    assert result is not None, output
    assert result["rows"] == [[row[0]] for row in expected_counts(port=server.port)]


@pytest.mark.parametrize(
    ("case", "threads"), [("single", 1), ("single", 4), ("multi", 1), ("multi", 4)]
)
def test_csv_counts(
    tmp_path: Path, server: LoopbackServer, case: str, threads: int
) -> None:
    result, output = run_probe(tmp_path, server, case, threads)
    assert result is not None, f"SFTP CSV read exceeded hard timeout:\n{output}"
    assert result["rows"] == expected_counts(single=case == "single", port=server.port)
    assert len(set(server.opened_paths)) == (1 if case == "single" else FILE_COUNT)


@pytest.mark.parametrize("case", ["single", "failure"])
def test_runtime_closes_connections(
    tmp_path: Path,
    server: LoopbackServer,
    case: str,
) -> None:
    result, output = run_probe(tmp_path, server, case, 1)
    assert result is not None, output
    assert result["rows"] == expected_counts(single=True, port=server.port)
    assert result["active_transports_after_run"] == 0, (
        "DuckDB session closed but an SSH transport remains alive before process exit"
    )


def test_timeout_dumps_stacks_and_reaps_child(
    tmp_path: Path, server: LoopbackServer
) -> None:
    server.stall_reads = True
    result, output = run_probe(tmp_path, server, "single", 1, timeout=5)
    assert result is None
    assert "Timeout" in output
    assert "_read_response" in output
    assert "sftp_file.py" in output
    assert server.transports
    assert all(not transport.is_active() for transport in server.transports)


@pytest.mark.parametrize("layer", ["paramiko", "fsspec", "duckdb"])
@pytest.mark.parametrize("threads", [1, 4])
@pytest.mark.parametrize("trace", [False, True], ids=["untraced", "traced"])
def test_layer_diagnostics(
    tmp_path: Path,
    server: LoopbackServer,
    layer: str,
    threads: int,
    trace: bool,
) -> None:
    result, output = run_probe(
        tmp_path, server, "multi", threads, layer=layer, trace=trace
    )
    if trace:
        summary = json.loads((tmp_path / "trace-summary.json").read_text())
        assert summary["client_events"] > 0
        assert summary["server_events"] > 0
        if threads == 1:
            # Pipelined directory EOF replies may legitimately be drained by
            # a later close. Only a different still-waiting thread is suspect.
            assert not summary["responses_consumed_by_other_pending_waiters"]
            assert not summary["overlapping_packet_reads"]
            assert not summary["pending_waiters"]
    assert result is not None, f"{layer} exceeded hard timeout:\n{output}"
    assert result["rows"] == expected_counts(
        port=server.port if layer == "duckdb" else None
    )
    if layer != "duckdb":
        assert result["active_transports_after_run"] == 0


@pytest.mark.parametrize("repeat", range(5))
@pytest.mark.parametrize("trace", [False, True], ids=["untraced", "traced"])
def test_turn_taking_four_thread_csv_reads(
    tmp_path: Path,
    server: LoopbackServer,
    repeat: int,
    trace: bool,
) -> None:
    result, output = run_probe(
        tmp_path, server, "multi", 4, turn_taking=True, trace=trace
    )
    assert result is not None, f"Turn-taking repeat {repeat} timed out:\n{output}"
    assert result["rows"] == expected_counts(port=server.port)
    assert len(set(server.opened_paths)) == FILE_COUNT
    stats = result["turn_taking"]
    assert len(stats) == 1
    assert len(stats[0]["threads"]) > 1, "Must exercise multiple real reader threads"
    assert stats[0]["contended_requests"] > 0, "Must exercise actual lock contention"
    if trace:
        summary = json.loads((tmp_path / "trace-summary.json").read_text())
        assert not summary["overlapping_packet_reads"]
        assert not summary["unexplained_response_mismatches"]
        assert not summary["responses_consumed_by_other_pending_waiters"]
        assert not summary["pending_waiters"]
        assert not summary["received_without_server_response"]


@pytest.mark.parametrize("layer", ["paramiko", "fsspec"])
@pytest.mark.parametrize("trace", [False, True], ids=["untraced", "traced"])
def test_turn_taking_mixed_listing_reads_and_errors(
    tmp_path: Path,
    server: LoopbackServer,
    layer: str,
    trace: bool,
) -> None:
    result, output = run_probe(
        tmp_path, server, "mixed", 4, layer=layer, turn_taking=True, trace=trace
    )
    assert result is not None, output
    assert result["rows"] == expected_counts()
    assert result["active_transports_after_run"] == 0
    assert len(result["turn_taking"][0]["threads"]) == 4
    assert result["turn_taking"][0]["contended_requests"] > 0
    if trace:
        summary = json.loads((tmp_path / "trace-summary.json").read_text())
        assert not summary["overlapping_packet_reads"]
        assert not summary["unexplained_response_mismatches"]
        assert not summary["responses_consumed_by_other_pending_waiters"]
        assert not summary["pending_waiters"]


@pytest.mark.parametrize("turn_taking", [False, True])
def test_turn_taking_runtime_failure_returns_promptly(
    tmp_path: Path,
    server: LoopbackServer,
    turn_taking: bool,
) -> None:
    result, output = run_probe(
        tmp_path, server, "failure", 4, turn_taking=turn_taking, trace=True
    )
    assert result is not None, output
    assert result["expected_failure"]
    assert result["rows"] == expected_counts(single=True, port=server.port)
    summary = json.loads((tmp_path / "trace-summary.json").read_text())
    assert not summary["pending_waiters"]
    assert result["active_transports_after_run"] == 0


def test_turn_taking_stalled_server_remains_bounded(
    tmp_path: Path,
    server: LoopbackServer,
) -> None:
    server.stall_reads = True
    result, output = run_probe(
        tmp_path, server, "multi", 4, turn_taking=True, trace=True, timeout=5
    )
    assert result is None
    assert "Timeout" in output
    assert "_read_response" in output
    assert "sftp_turn_taking.py" in output
    assert all(not transport.is_active() for transport in server.transports)


@pytest.mark.parametrize("repeat", range(5))
@pytest.mark.parametrize("trace", [False, True], ids=["untraced", "traced"])
def test_registered_sftp_serializes_concurrent_reads(
    tmp_path: Path, server: LoopbackServer, repeat: int, trace: bool
) -> None:
    # Normal production selection: no test replacement of SSH or SFTP clients.
    result, output = run_probe(tmp_path, server, "multi", 4, trace=trace)
    assert result is not None, f"Production repeat {repeat} timed out:\n{output}"
    assert result["turn_taking"] == []
    assert result["rows"] == expected_counts(port=server.port)
    assert len(set(server.opened_paths)) == FILE_COUNT
    if trace:
        summary = json.loads((tmp_path / "trace-summary.json").read_text())
        assert not summary["overlapping_packet_reads"]
        assert not summary["unexplained_response_mismatches"]
        assert not summary["responses_consumed_by_other_pending_waiters"]
        assert not summary["pending_waiters"]
        assert not summary["received_without_server_response"]


@pytest.mark.parametrize("trust", ["matching", "mismatched", "absent"])
def test_fingerprint_registration_before_authentication(
    tmp_path: Path, server: LoopbackServer, trust: str
) -> None:
    from pydantic import SecretStr

    from quackframe.sql_functions.register_filesystem.models import SftpFilesystem

    fingerprint = {
        "matching": server.host_key.fingerprint,
        "mismatched": "SHA256:" + "A" * 43,
        "absent": None,
    }[trust]
    credentials = SftpFilesystem(
        username=SecretStr("reader"),
        key_path=str(tmp_path / "client_key"),
        port=server.port,
        scope="sftp://127.0.0.1",
        host_key_fingerprint=fingerprint,
    )
    if trust == "mismatched":
        with pytest.raises(RuntimeError, match="host-key fingerprint"):
            credentials.create_filesystem("fingerprint")
        assert server.authentication_attempts == 0
        assert all(not transport.is_authenticated() for transport in server.transports)
        assert not server.subsystems
    else:
        filesystem = credentials.create_filesystem("fingerprint")
        try:
            assert (
                len(filesystem.ls(f"fingerprint://127.0.0.1{REMOTE}")) == FILE_COUNT + 1
            )
        finally:
            filesystem.close_backend()
    server.wait_disconnected()


def test_two_endpoints_and_another_type_share_one_session(
    tmp_path: Path, server: LoopbackServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    import duckdb
    from test_register_filesystem import MemoryFilesystem

    from quackframe.credential_loading import loading
    from quackframe.resources import SessionResources
    from quackframe.sql_functions.installer import install_functions
    from quackframe.sql_functions.register_filesystem import models

    other_root = tmp_path / "other-remote"
    other_root.mkdir()
    (other_root / "report.csv").write_text("value\n99\n")
    other = LoopbackServer(other_root)
    other_key = tmp_path / "other_key"
    other.user_key.write_private_key_file(str(other_key))
    other.thread.start()

    def resolve(reference: str, model_type: Any) -> Any:
        if reference == "memory-files":
            return model_type()
        target = server if reference == "first-files" else other
        key = tmp_path / "client_key" if target is server else other_key
        return model_type(
            username="reader",
            key_path=str(key),
            port=target.port,
            scope="sftp://127.0.0.1",
            host_key_fingerprint=target.host_key.fingerprint,
        )

    provider = Mock()
    provider.resolve.side_effect = resolve
    monkeypatch.setattr(loading, "get_provider", Mock(return_value=provider))
    monkeypatch.setitem(models.FILESYSTEM_MODELS, "test_memory", MemoryFilesystem)
    try:
        with duckdb.connect() as connection:
            with SessionResources(connection) as resources:
                install_functions(connection, ("register_filesystem",), resources)
                for reference, kind in [
                    ("first-files", "sftp"),
                    ("second-files", "sftp"),
                    ("memory-files", "test_memory"),
                ]:
                    connection.execute(
                        "SELECT quackframe.register_filesystem('example', ?, ?)",
                        [reference, kind],
                    )
                paths = connection.execute(
                    f"SELECT file FROM glob('first-files://127.0.0.1{REMOTE}/daily_trips-2026_09_01.csv')"
                ).fetchall()
                assert paths == [
                    (
                        f"first-files://127.0.0.1:{server.port}{REMOTE}/daily_trips-2026_09_01.csv",
                    )
                ]
                assert (
                    connection.execute(
                        "SELECT octet_length(content) FROM read_blob(?)",
                        [[paths[0][0]]],
                    ).fetchall()[0][0]
                    > 0
                )
                assert connection.execute(
                    "SELECT * FROM read_csv('second-files://127.0.0.1/report.csv')"
                ).fetchall() == [(99,)]
                assert connection.execute(
                    "SELECT * FROM read_csv('memory-files:///report.csv')"
                ).fetchall() == [(42,)]
                with pytest.raises(duckdb.Error, match="registered endpoint"):
                    connection.execute(
                        "SELECT * FROM read_csv('second-files://wrong.test/report.csv')"
                    )
                server.writable = other.writable = True
                for protocol, value in [("first-files", 17), ("second-files", 29)]:
                    connection.execute(
                        "CREATE OR REPLACE TEMP TABLE export_data AS SELECT ? AS value",
                        [value],
                    )
                    connection.execute(
                        "COPY export_data TO ? (FORMAT CSV)",
                        [f"{protocol}://127.0.0.1/written.csv"],
                    )
                    assert connection.execute(
                        "SELECT value FROM read_csv(?)",
                        [f"{protocol}://127.0.0.1/written.csv"],
                    ).fetchall() == [(value,)]
                assert (server.root / "written.csv").read_text() == "value\n17\n"
                assert (other.root / "written.csv").read_text() == "value\n29\n"
                with pytest.raises(duckdb.Error, match="registered endpoint"):
                    connection.execute(
                        "COPY (SELECT 1) TO 'second-files://wrong.test/written.csv' "
                        "(FORMAT CSV)"
                    )
            assert connection.list_filesystems() == []
        server.wait_disconnected()
        other.wait_disconnected()
        assert all(not t.is_active() for t in server.transports + other.transports)
    finally:
        other.close()
