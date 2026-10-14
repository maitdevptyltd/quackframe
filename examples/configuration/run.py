"""Load project configuration and override database storage for a Python run."""

from pathlib import Path

from quackframe import load_config, run

config = load_config(
    root=Path(__file__).resolve().parent,
    database_mode="persistent",
    database_path="data/example.duckdb",
    runtime="direct",
)

result = run(["sql/example.sql"], config=config)
print(result)
