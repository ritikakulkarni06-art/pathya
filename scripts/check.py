"""Cross-platform equivalent of make check; uses the current virtual environment."""

import subprocess
import sys


def main() -> None:
    for args in [
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        ["mypy"],
        ["pytest", "-q"],
    ]:
        subprocess.run([sys.executable, "-m", *args], check=True)


if __name__ == "__main__":
    main()
