"""Command-line entry point for the shared Quackframe engine."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from quackframe.api import run
from quackframe.config import load_config
from quackframe.errors import ConfigurationError, ExecutionError, QuackframeError
from quackframe.runtimes.registry import runtime_names


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface from shared public registries."""

    parser = argparse.ArgumentParser(prog="quackframe")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run ordered SQL files")
    run_parser.add_argument("sql_files", nargs="+")
    run_parser.add_argument("--runtime", choices=runtime_names())
    run_parser.add_argument("--config", type=Path)
    run_parser.add_argument("--root", type=Path)

    database_group = run_parser.add_mutually_exclusive_group()
    database_group.add_argument("--memory", action="store_true")
    database_group.add_argument("--temporary", action="store_true")
    database_group.add_argument("--database-path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run ordered SQL files and return a scheduler-friendly process status.

    Configuration failures return ``2``. Execution and other Quackframe
    failures return ``1`` without exposing SQL text or sensitive values.
    """

    arguments = build_parser().parse_args(argv)
    database_mode = None
    if arguments.memory:
        database_mode = "memory"
    elif arguments.temporary:
        database_mode = "temporary"
    elif arguments.database_path is not None:
        database_mode = "persistent"

    try:
        config = load_config(
            config_path=arguments.config,
            root=arguments.root,
            runtime=arguments.runtime,
            database_mode=database_mode,
            database_path=arguments.database_path,
        )
        result = run(arguments.sql_files, config=config)
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except ExecutionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except QuackframeError as error:
        print(f"Quackframe error: {error}", file=sys.stderr)
        return 1

    print(
        f"Completed {len(result.files)} SQL file(s), "
        f"{result.statement_count} statement(s), runtime={result.runtime}"
    )
    return 0
