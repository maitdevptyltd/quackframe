"""Run default-branch release tools without importing from the build tree."""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    if not sys.flags.isolated:
        raise ValueError("Release entrypoint requires Python isolated mode (-I).")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    parser.add_argument(
        "module", choices=["release_workflow", "release_artifacts", "package_smoke"]
    )
    args, remaining = parser.parse_known_args()
    # -I excludes cwd, PYTHONPATH and user site packages. Add only the checkout
    # containing this trusted entrypoint, even when Git operates on candidate data.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if args.repository:
        os.chdir(args.repository)
    sys.argv = [args.module, *remaining]
    runpy.run_module(f"scripts.{args.module}", run_name="__main__")


if __name__ == "__main__":
    main()
