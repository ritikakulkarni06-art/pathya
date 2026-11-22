import ast
import json
import threading
from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from scripts.demo import run_demo
from scripts.export_contracts import generated_contracts
from scripts.export_contracts import main as export_contracts
from scripts.license_report import inventory
from scripts.seed_demo import seed_demo


def test_additive_endpoint_contract_has_examples_and_safe_problem_catalog():
    schema = create_app(Settings(_env_file=None, pathya_env="test")).openapi()
    paths = schema["paths"]
    for path, method in [
        ("/documents", "post"),
        ("/jobs/{job_id}", "get"),
        ("/documents/{document_id}/manifest", "get"),
        ("/blocks/{block_id}", "patch"),
        ("/questions", "post"),
        ("/documents/{document_id}", "delete"),
    ]:
        assert method in paths[path]
    assert "202" in paths["/documents"]["post"]["responses"]
    assert "409" in paths["/blocks/{block_id}"]["patch"]["responses"]
    assert paths["/documents/{document_id}/manifest"]["get"]["responses"]["410"]["content"][
        "application/problem+json"
    ]["examples"]["deleted"]["value"]["purge_local_copy"]
    for methods in paths.values():
        for method, operation in methods.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            assert "default" in operation["responses"]
            for content in operation.get("requestBody", {}).get("content", {}).values():
                assert "examples" in content
            for status, response in operation["responses"].items():
                if status.startswith("2") and status != "204":
                    assert any(
                        "examples" in content or "example" in content
                        for content in response["content"].values()
                    )
            if "422" in operation["responses"]:
                assert "application/problem+json" in operation["responses"]["422"]["content"]
    catalog = schema["x-pathya-error-catalog"]
    for path in Path("app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Problem"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                assert node.args[1].value in catalog
    for code, entry in catalog.items():
        assert entry["example"]["code"] == code
        assert {"type", "title", "status", "detail", "code"} <= set(entry["example"])


def test_contract_export_is_deterministic_and_stale_files_fail(tmp_path, monkeypatch):
    expected = generated_contracts()
    assert expected == generated_contracts()
    monkeypatch.chdir(tmp_path)
    export_contracts()
    export_contracts(check=True)
    (tmp_path / "contracts/openapi.json").write_text("{}")
    with pytest.raises(SystemExit, match="stale"):
        export_contracts(check=True)


def test_installed_license_report_names_versions_and_review_status():
    rows = inventory()
    names = {r["name"].lower().replace("_", "-") for r in rows}
    assert {"fastapi", "pypdf", "pillow", "argon2-cffi", "httpx"} <= names
    assert all(
        r["version"] and r["license"] and "Review required" in r["redistribution"] for r in rows
    )
    assert "GEMINI_API_KEY" not in json.dumps(rows)


def test_live_demo_smoke_starts_and_stops_owned_api_and_worker(tmp_path):
    result = run_demo(tmp_path / "demo", port=0, smoke=True)
    assert result["smoke_passed"] and result["llm_enabled"] is False
    assert all(thread.name != "pathya-demo-api" for thread in threading.enumerate())


def test_demo_rejects_nonempty_directory_without_demo_marker(tmp_path):
    database = tmp_path / "pathya.sqlite3"
    database.write_bytes(b"existing data")
    with pytest.raises(ValueError, match="empty directory or a recognized synthetic demo"):
        seed_demo(tmp_path)
    assert database.read_bytes() == b"existing data"
