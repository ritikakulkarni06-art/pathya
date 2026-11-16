"""Inventory installed distribution metadata; manual redistribution review remains required."""

from importlib.metadata import distributions
from pathlib import Path


def main() -> None:
    rows = [
        "# Dependency inventory",
        "",
        "Resolved for Python 3.12. Versions are pinned in requirements.lock. License metadata is recorded as supplied by each distribution, not legal advice. Redistribution review: pending for every entry. Native bundled code requires separate review.",
        "",
        "| Distribution | Version | Declared license | Purpose | Redistribution |",
        "| --- | --- | --- | --- | --- |",
    ]
    for distribution in sorted(
        distributions(), key=lambda item: (item.metadata.get("Name") or "").lower()
    ):
        name = distribution.metadata.get("Name", "unknown")
        license_text = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "; ".join(
                item.rsplit(" :: ", 1)[-1]
                for item in distribution.metadata.get_all("Classifier", [])
                if item.startswith("License ::")
            )
            or "Not declared; inspect license files"
        )
        license_text = " ".join(license_text.split()).replace("|", "/")[:150]
        rows.append(
            f"| {name} | {distribution.version} | {license_text} | Runtime, tooling or transitive dependency | Pending review |"
        )
    rows.extend(
        [
            "",
            "Python/SQLite use the standard library; SQLite is public domain. No E5 model, numpy, eSpeak, PDFium or PDF parser is included yet. No cloud API has been enabled.",
        ]
    )
    Path("docs/DEPENDENCIES.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
