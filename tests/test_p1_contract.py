import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.adapters.p1 import parse_p1_payload, validate_p1_initial_import
from app.errors import Problem

FIXTURES = Path(__file__).parent / "fixtures" / "p1_contract"
VECTORS = json.loads((FIXTURES / "index.json").read_bytes())["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=[case["file"] for case in VECTORS])
def test_pinned_contract_vectors(vector):
    raw = (FIXTURES / vector["file"]).read_bytes()
    document = json.loads(raw)
    for minor in (0, 1):
        schema = json.loads((FIXTURES / f"pathya_content.v1.{minor}.0.schema.json").read_bytes())
        expected = vector["expected_valid"][f"schema_1_{minor}_0"]
        assert Draft202012Validator(schema).is_valid(document) is expected
    if vector["expected_valid"]["python"]:
        result = parse_p1_payload(raw)
        assert result.source_json == raw
        assert json.loads(result.source_json) == document
    else:
        with pytest.raises(Problem, match="invalid_p1_document"):
            parse_p1_payload(raw)


def test_initial_import_checks_source_and_backend_revision_authority():
    raw = (FIXTURES / "valid_v1_1_0_status_and_flags.json").read_bytes()
    document = json.loads(raw)
    checksum = document["source_asset"]["sha256"]
    with pytest.raises(Problem, match="source_checksum_mismatch"):
        validate_p1_initial_import(raw, "0" * 64)
    with pytest.raises(Problem, match="producer_revision_history"):
        validate_p1_initial_import(raw, checksum)

    document["corrections"] = []
    for block in document["blocks"]:
        block["revision"] = 1
        block["current_text"] = block["raw_text"]
    initial = json.dumps(document).encode()
    assert validate_p1_initial_import(initial, checksum).source_json == initial

    document["blocks"][0]["revision"] = 2
    with pytest.raises(Problem, match="producer_revision_history"):
        validate_p1_initial_import(json.dumps(document).encode(), checksum)
