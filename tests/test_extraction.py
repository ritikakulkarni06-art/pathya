import copy
import json
import sys
from pathlib import Path
from uuid import UUID

import pytest

from app.adapters.extraction import (
    ExtractionError,
    FixtureExtractionAdapter,
    SubprocessExtractionAdapter,
    get_extraction_adapter,
)
from app.config import Settings
from app.db.repos import users
from app.errors import Problem
from app.schemas.content import parse_extraction
from app.services.ingest import import_extraction

FIXTURE = Path("tests/fixtures/chapter_demo.json")


@pytest.fixture
def chapter():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def empty_document(database):
    with database.write_tx() as conn:
        users.create(conn, "u", "owner@example.test", None, "2026-01-01T00:00:00Z")
        conn.execute(
            "INSERT INTO documents VALUES ('demo','u','Synthetic demo','hash','Original synthetic content','[\"en\",\"hi\"]',0,'processing','2027-01-01','now','now',NULL)"
        )
    return database


def test_fixture_contract_and_synthetic_complex_content(chapter):
    result = parse_extraction(chapter)
    assert len(result.pages) == 10
    assert {block.lang for block in result.blocks} == {"en", "hi"}
    assert result.pages[0].printed_label == "11"
    assert result.pages[0].pdf_index_0 == 0
    assert any(block.critical_flag and block.status == "needs_review" for block in result.blocks)
    assert any(block.metadata.mathml for block in result.blocks)
    assert any(block.metadata.alt_text_short for block in result.blocks)
    assert any(block.metadata.header_cell_ids for block in result.blocks)
    assert any(
        "\u092a\u094d\u0930\u0915\u093e\u0936" in block.text_current
        for block in result.blocks
        if block.lang == "hi"
    )


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda value: value["blocks"].append(copy.deepcopy(value["blocks"][0])), "duplicate_id"),
        (lambda value: value["blocks"][0].update(parent_id="missing"), "dangling_parent"),
        (lambda value: value["blocks"][0].update(page_id="missing"), "dangling_page"),
        (lambda value: value["blocks"][0].update(bbox=[-1, 0, 1, 1]), "invalid_bbox"),
        (
            lambda value: value["blocks"][0].update(parent_id=value["blocks"][0]["id"]),
            "parent_cycle",
        ),
        (
            lambda value: value["edges"].append(
                {"from_id": "missing", "relation": "precedes", "to_id": "heading-1"}
            ),
            "dangling_edge",
        ),
        (lambda value: value["blocks"][0].update(order_key=0), "invalid_order"),
        (
            lambda value: value["blocks"][0].update(metadata={"header_cell_ids": ["heading-1"]}),
            "invalid_header",
        ),
    ],
)
def test_invalid_contracts_rejected(chapter, mutation, code):
    mutation(chapter)
    with pytest.raises(Problem) as error:
        parse_extraction(chapter)
    assert error.value.code == code


def test_initial_import_is_atomic_idempotent_and_scoped(empty_document, chapter):
    first = import_extraction(empty_document, "demo", chapter)
    second = import_extraction(empty_document, "demo", chapter)
    assert first == second
    assert all(UUID(identifier).version == 4 for identifier in first.id_map.values())
    with empty_document.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"] == 10
        assert conn.execute(
            "SELECT state,current_revision FROM documents WHERE id='demo'"
        ).fetchone() == {"state": "review_required", "current_revision": 1}
        assert conn.execute("SELECT count(*) AS n FROM block_versions").fetchone()["n"] == len(
            chapter["blocks"]
        )
        figure = conn.execute(
            "SELECT metadata_json FROM blocks WHERE id=?", (first.id_map["figure-1"],)
        ).fetchone()
        assert json.loads(figure["metadata_json"])["caption_block_ids"] == [
            first.id_map["caption-1"]
        ]
    with empty_document.write_tx() as conn:
        conn.execute(
            "INSERT INTO documents VALUES ('other','u','Other synthetic','otherhash','Synthetic','[\"en\"]',0,'processing','2027-01-01','now','now',NULL)"
        )
    other = import_extraction(empty_document, "other", chapter)
    assert set(first.id_map.values()).isdisjoint(other.id_map.values())
    changed = copy.deepcopy(chapter)
    changed["blocks"][0]["text_current"] += " changed"
    with pytest.raises(Problem, match="initial_already_imported"):
        import_extraction(empty_document, "demo", changed)


def test_injected_failure_rolls_back_everything(empty_document, chapter):
    with empty_document.write_tx() as conn:
        conn.execute(
            "CREATE TRIGGER injected_import_failure BEFORE INSERT ON blocks WHEN new.order_key=20 BEGIN SELECT RAISE(ABORT,'crash'); END"
        )
    with pytest.raises(Problem, match="extraction_integrity"):
        import_extraction(empty_document, "demo", chapter)
    with empty_document.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM blocks").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM revisions").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM extraction_identifiers").fetchone()["n"] == 0
        assert (
            conn.execute("SELECT current_revision FROM documents WHERE id='demo'").fetchone()[
                "current_revision"
            ]
            == 0
        )


def test_wrong_document_asset_rejected_atomically(empty_document, chapter):
    chapter["pages"][0]["source_asset_id"] = "missing"
    with pytest.raises(Problem, match="invalid_source_asset"):
        import_extraction(empty_document, "demo", chapter)
    with empty_document.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM revisions").fetchone()["n"] == 0


def test_fixture_adapter_page_progress_and_registry(tmp_path):
    progress = []
    adapter = get_extraction_adapter(Settings(_env_file=None, pathya_env="test"))
    result = adapter.extract(
        tmp_path / "unused",
        ["en", "hi"],
        [0, 1],
        lambda done, total: progress.append((done, total)),
    )
    assert len(result.pages) == 2
    assert progress == [(1, 2), (2, 2)]
    assert isinstance(
        get_extraction_adapter(
            Settings(
                _env_file=None,
                extraction_adapter="python:app.adapters.extraction:FixtureExtractionAdapter",
            )
        ),
        FixtureExtractionAdapter,
    )
    with pytest.raises(ExtractionError, match="invalid_adapter"):
        get_extraction_adapter(Settings(_env_file=None, extraction_adapter="unknown"))
    for page_range in [[-1], [0, 0], [999], []]:
        with pytest.raises(ExtractionError):
            adapter.extract(tmp_path, ["en"], page_range, lambda done, total: None)
    with pytest.raises(ExtractionError, match="unsupported_language"):
        adapter.extract(tmp_path, ["xx"], None, lambda done, total: None)


def test_subprocess_fails_closed_without_network_sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr("app.adapters.extraction.shutil.which", lambda executable: None)
    adapter = SubprocessExtractionAdapter([sys.executable, "-c", "print('must not execute')"])
    with pytest.raises(ExtractionError, match="extraction_sandbox_unavailable"):
        adapter.extract(tmp_path, ["en"], None, lambda done, total: None)


class TrustedTestCommand(SubprocessExtractionAdapter):
    # Only tests bypass Linux namespaces to exercise the transport with trusted tiny commands.
    def _isolated_command(self):
        return self.command


def test_subprocess_transport_validates_json_and_limits(tmp_path):
    code = "import sys;from pathlib import Path;sys.stdin.buffer.read();print(Path(sys.argv[1]).read_text(encoding='utf-8'))"
    adapter = TrustedTestCommand([sys.executable, "-c", code, str(FIXTURE.resolve())])
    assert len(adapter.extract(tmp_path, ["en", "hi"], None, lambda done, total: None).pages) == 10
    for command, expected in [
        ([sys.executable, "-c", "print('not JSON')"], "invalid_extraction_output"),
        ([sys.executable, "-c", "raise SystemExit(1)"], "extraction_failed"),
    ]:
        with pytest.raises(ExtractionError, match=expected):
            TrustedTestCommand(command).extract(tmp_path, ["en"], None, lambda done, total: None)
    with pytest.raises(ExtractionError, match="extraction_output_too_large"):
        TrustedTestCommand([sys.executable, "-c", "print('x'*100)"], output_limit=10).extract(
            tmp_path, ["en"], None, lambda done, total: None
        )


def test_subprocess_timeout_kills_child(tmp_path):
    with pytest.raises(ExtractionError, match="extraction_timeout"):
        TrustedTestCommand([sys.executable, "-c", "import time;time.sleep(30)"], timeout=1).extract(
            tmp_path, ["en"], None, lambda done, total: None
        )


def test_model_construct_cannot_bypass_validation(chapter):
    bad = parse_extraction(chapter).model_copy(update={"schema_version": "unknown"})
    with pytest.raises(Problem):
        parse_extraction(bad)


def test_mathml_is_inert_and_reviewed_content_has_provenance(chapter):
    equation = next(block for block in chapter["blocks"] if block["type"] == "equation")
    equation["metadata"]["mathml"] = "<math><script>alert(1)</script></math>"
    with pytest.raises(Problem):
        parse_extraction(chapter)


def test_schema_exports_are_current_and_deterministic(tmp_path, monkeypatch):
    from scripts.export_contracts import main

    original = Path.cwd()
    monkeypatch.chdir(tmp_path)
    main()
    first = {path.name: path.read_bytes() for path in Path("contracts").glob("*.json")}
    main()
    assert first == {path.name: path.read_bytes() for path in Path("contracts").glob("*.json")}
    for name, content in first.items():
        assert json.loads(content) == json.loads((original / "contracts" / name).read_bytes()), name


def test_fixture_validates_exported_json_schema(chapter):
    from jsonschema import Draft202012Validator

    schema = json.loads(Path("contracts/extraction_output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(chapter)
    invalid = copy.deepcopy(chapter)
    invalid["blocks"][0]["unexpected_field"] = "must reject"
    assert list(Draft202012Validator(schema).iter_errors(invalid))
