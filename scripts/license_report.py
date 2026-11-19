"""Report installed distribution metadata; this is not legal redistribution approval."""

import argparse
import importlib.metadata
import json
from typing import Any

PURPOSES = {
    "fastapi": "API framework",
    "uvicorn": "Single API server",
    "pydantic": "Strict boundary schemas",
    "pydantic-settings": "Environment configuration",
    "httpx": "HTTP adapter/client and API tests",
    "argon2-cffi": "Argon2id password hashing",
    "argon2-cffi-bindings": "Native Argon2 binding",
    "pypdf": "Bounded PDF inspection and synthetic demo PDF creation",
    "pillow": "Image validation and metadata stripping",
    "python-multipart": "Bounded multipart parsing",
    "orjson": "JSON support",
    "pytest": "Behavioral and integration tests",
    "pytest-asyncio": "Async integration tests",
    "ruff": "Lint and formatting",
    "mypy": "Strict application type checks",
    "coverage": "Database coverage gate",
    "jsonschema": "Contract schema checks",
}


def inventory() -> list[dict[str, Any]]:
    rows = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        license_value = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or ""
        )
        classifiers = [
            value.rsplit(" :: ", 1)[-1]
            for value in distribution.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        ]
        if not license_value.strip() or len(license_value) > 160 or "\n" in license_value:
            license_value = (
                "; ".join(classifiers)
                or "See distribution LICENSE files; normalization/review required"
            )
        rows.append(
            {
                "name": name,
                "version": distribution.version,
                "license": license_value.strip(),
                "purpose": PURPOSES.get(
                    name.lower().replace("_", "-"),
                    "Transitive runtime, build or development dependency",
                ),
                "redistribution": "Review required; not automatically approved",
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print installed dependency/license metadata without a network request."
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = inventory()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("Name\tVersion\tDeclared license\tPurpose\tRedistribution")
        for row in rows:
            print(
                "\t".join(
                    str(row[key])
                    for key in ["name", "version", "license", "purpose", "redistribution"]
                )
            )


if __name__ == "__main__":
    main()
