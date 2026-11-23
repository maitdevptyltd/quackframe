import subprocess
import sys
from collections.abc import Sequence


def main(arguments: Sequence[str]) -> int:
    command = ["poetry", "run", "quackframe", "run", *arguments]

    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print(
            "Quackframe could not start because Poetry is not on PATH.",
            file=sys.stderr,
        )
        return 127


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
