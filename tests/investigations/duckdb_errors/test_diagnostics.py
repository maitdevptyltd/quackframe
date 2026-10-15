"""Run only bounded child probes; optional output is an empirical evidence file."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from .probe import SCENARIOS


@pytest.fixture(scope="session")
def observations() -> Iterator[list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    yield records
    destination = os.environ.get("DUCKDB_INVESTIGATION_OUTPUT")
    if destination:
        Path(destination).write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


@pytest.mark.parametrize("scenario_id", [scenario.id for scenario in SCENARIOS])
@pytest.mark.parametrize("mode", ["text", "json"])
def test_diagnostic_probe(
    scenario_id: str, mode: str, observations: list[dict[str, Any]]
) -> None:
    command = [
        sys.executable,
        str(Path(__file__).with_name("probe.py")),
        scenario_id,
        mode,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        observations.append({"id": scenario_id, "mode": mode, "status": "timeout"})
        pytest.fail(f"Probe {scenario_id}/{mode} exceeded 15 seconds; do not retry")
    assert completed.returncode == 0, completed.stderr
    record = json.loads(completed.stdout)
    observations.append(record)
    assert record["runtime"]["duckdb"] == "1.5.5", "Reassess findings for a new version"
    assert record["status"] == "error_observed", record
    assert record["exception"]["message"]
