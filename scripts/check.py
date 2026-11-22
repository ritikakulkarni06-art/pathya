"""Cross-platform equivalent of make check; uses the current virtual environment."""

import subprocess
import sys


def main() -> None:
    for args in [
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        ["mypy"],
        ["scripts.export_contracts", "--check"],
        ["coverage", "run", "-m", "pytest", "-q", "-x", "--tb=short"],
        ["coverage", "report", "--include=app/db/*", "--fail-under=85"],
    ]:
        subprocess.run([sys.executable, "-m", *args], check=True)


if __name__ == "__main__":
    main()
