"""Child-process probe for the real loopback SFTP integration tests."""

from __future__ import annotations

import csv
import faulthandler
import gc
import importlib.abc
import importlib.metadata
import io
import json
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar, TypeVar, cast

import duckdb
from paramiko import AutoAddPolicy, SFTPClient, SSHClient, Transport
from sftp_trace import PacketTrace
from sftp_turn_taking import enable_turn_taking, observations

from quackframe import QuackframeConfig, run
from quackframe.credential_loading.models import CredentialModel
from quackframe.credential_loading.providers import registry
from quackframe.errors import ExecutionError

T = TypeVar("T", bound=CredentialModel)


class NoPrefect(importlib.abc.MetaPathFinder):
    """Fail before any accidental Prefect import could start a local server."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname == "prefect" or fullname.startswith("prefect."):
            raise ModuleNotFoundError(
                "Prefect is forbidden in this probe", name=fullname
            )
        return None


class LoopbackProvider:
    """Supply temporary credentials through the ordinary provider registry."""

    values: ClassVar[dict[str, object]] = {}
    calls: ClassVar[int] = 0

    def resolve(self, reference: str, model_type: type[T]) -> T:
        assert reference == "temporary-local-key"
        assert model_type.credential_type == "ssh_private_key"
        type(self).calls += 1
        return model_type.model_validate(self.values)


def run_library_control(root: Path, settings: dict[str, Any]) -> list[list[object]]:
    """Read the same files on one shared real client, without DuckDB or its GIL path."""
    client = None
    filesystem: Any = None
    ftp: Any = None
    try:
        options: dict[str, Any] = {
            "username": "reader",
            "key_filename": str(root / "client_key"),
            "port": settings["port"],
        }
        if settings["layer"] == "paramiko":
            client = SSHClient()
            client.set_missing_host_key_policy(AutoAddPolicy())
            client.connect("127.0.0.1", **options)
            ftp = client.open_sftp()
            assert ftp is not None
        else:
            from fsspec.implementations.sftp import (  # pyright: ignore[reportMissingTypeStubs]
                SFTPFileSystem,
            )

            filesystem = SFTPFileSystem(
                host="127.0.0.1", skip_instance_cache=True, **options
            )
            ftp = filesystem.ftp
            client = filesystem.client

        def count_file(day: int) -> list[object]:
            path = f"/from_test/trips/daily_trips-2026_09_{day:02}.csv"
            if settings["case"] == "mixed" and day % 5 == 0:
                # Exercise directory discovery alongside file reads, then prove
                # an SFTP error releases the lock and later requests progress.
                if filesystem is None:
                    names = [
                        entry.filename for entry in ftp.listdir_iter("/from_test/trips")
                    ]
                    assert len([name for name in names if name.endswith(".csv")]) == 26
                else:
                    assert len(filesystem.glob("/from_test/trips/*.csv")) == 26
                try:
                    ftp.stat("/from_test/trips/missing.csv")
                except OSError as error:
                    assert error.errno == 2
                else:
                    raise AssertionError("Missing SFTP file unexpectedly exists")
            if filesystem is None:
                ftp.stat(path)
                handle = ftp.open(path, "rb")
            else:
                filesystem.info(path)
                handle = filesystem.open(path, "rb")
            with handle:
                content = cast(bytes, handle.read())
            rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
            assert rows[0] == (
                ["trip_id", "payload", "optional"]
                if day % 2
                else ["payload", "trip_id"]
            )
            assert all(len(row) == len(rows[0]) for row in rows[1:])
            return [f"sftp://{path}", len(rows) - 1]

        with ThreadPoolExecutor(max_workers=settings["threads"]) as executor:
            return list(executor.map(count_file, range(1, 27)))
    finally:
        # Controls explicitly own their clients. Production-runtime cleanup is
        # tested separately and is never repaired by diagnostic instrumentation.
        if ftp is not None:
            ftp.close()
        if client is not None:
            client.close()


def main() -> None:
    root = Path(sys.argv[1])
    settings = json.loads((root / "settings.json").read_text())
    # This watchdog does not need the main thread to return from DuckDB. The
    # parent owns termination; dumping threads must never be our only timeout.
    faulthandler.enable()
    faulthandler.dump_traceback_later(settings["dump_after"], repeat=True)
    sys.meta_path.insert(0, NoPrefect())
    LoopbackProvider.values = {
        "username": "reader",
        "key_path": str(root / "client_key"),
        "port": settings["port"],
        "scope": "sshfs://127.0.0.1",
    }
    registry.PROVIDER_REGISTRY = (
        registry.ProviderRegistration(
            name="loopback",
            module_name=__name__,
            implementation_name="LoopbackProvider",
            missing_dependency="unused",
            missing_dependency_message="The test provider is local",
        ),
    )
    versions = {
        name: importlib.metadata.version(name)
        for name in ("quackframe", "duckdb", "fsspec", "paramiko", "pydantic", "pytest")
    }
    print(json.dumps({"python": sys.version, "versions": versions}), flush=True)
    if settings["layer"] != "duckdb":
        started = time.monotonic()
        rows = run_library_control(root, settings)
        time.sleep(0.5)
        active = sum(
            isinstance(t, Transport) and t.is_active() for t in threading.enumerate()
        )
        result = {
            "rows": rows,
            "active_transports_after_run": active,
            "elapsed": time.monotonic() - started,
            "versions": versions,
            "python": sys.version,
            "layer": settings["layer"],
            "turn_taking": observations(),
        }
        (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
        print(json.dumps(result), flush=True)
        faulthandler.cancel_dump_traceback_later()
        return
    database = root / "result.duckdb"
    config = QuackframeConfig.model_validate(
        {
            "root": root,
            "runtime": "direct",
            "log_setting": "none",
            "functions": {"enabled": ["register_filesystem"]},
            "database": {"mode": "persistent", "path": database},
        }
    )
    started = time.monotonic()
    failed = False
    try:
        run([root / "register.sql", root / "probe.sql"], config=config)
    except ExecutionError as error:
        if settings["case"] != "failure":
            raise
        assert error.sql_file == root / "probe.sql"
        assert error.statement_number == 3
        assert "requested file" in error.reason or "missing.csv" in error.reason
        failed = True
    assert failed == (settings["case"] == "failure")
    assert LoopbackProvider.calls == 1
    assert LoopbackProvider.values["scope"] == "sshfs://127.0.0.1"
    assert not any(
        name == "prefect" or name.startswith("prefect.") for name in sys.modules
    )

    with duckdb.connect(str(database)) as connection:
        assert not connection.filesystem_is_registered("temporary-local-key")
        rows = connection.execute("SELECT * FROM result ORDER BY 1").fetchall()
        if settings["case"] == "failure":
            assert connection.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'must_not_run'"
            ).fetchone() == (0,)
    # Observe runtime cleanup while this process is still alive. Process exit
    # would otherwise hide sockets left open after both success and SQL failure.
    gc.collect()
    time.sleep(0.5)
    active = sum(
        isinstance(thread, Transport) and thread.is_active()
        for thread in threading.enumerate()
    )
    result = {
        "rows": rows,
        "active_transports_after_run": active,
        "elapsed": time.monotonic() - started,
        "expected_failure": failed,
        "turn_taking": observations(),
        "versions": versions,
        "python": sys.version,
    }
    (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result), flush=True)
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    probe_root = Path(sys.argv[1])
    probe_settings = json.loads((probe_root / "settings.json").read_text())
    with ExitStack() as resources:
        if probe_settings["trace"]:
            trace = PacketTrace(probe_root / "client-trace.jsonl", "client")
            resources.callback(trace.close)
            resources.enter_context(trace.instrument(SFTPClient))
        if probe_settings.get("turn_taking", False):
            resources.enter_context(enable_turn_taking())
        try:
            main()
        except Exception as error:
            # Preserve the traceback and nonzero exit, while letting the parent
            # distinguish the known upstream race from unrelated child failures.
            (probe_root / "error.json").write_text(
                json.dumps(
                    {
                        "type": f"{type(error).__module__}.{type(error).__qualname__}",
                        "message": str(error),
                    }
                ),
                encoding="utf-8",
            )
            raise
