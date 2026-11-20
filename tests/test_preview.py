import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject

from app.config import Settings
from app.preview import create_app
from app.services.ingest import import_extraction
from tests.test_uploads import upload
from tests.test_uploads import upload_client as upload_client


def test_same_origin_reader_mount_keeps_api_and_static_fallback_separate(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<title>Pathya test</title>", encoding="utf-8")
    (dist / ".env").write_text("private marker", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path / "data",
        reader_dist=dist,
        auth_mode="session",
        session_secret="test-secret" * 4,
    )
    with TestClient(create_app(settings), base_url="https://preview.test") as client:
        assert client.get("/").text == "<title>Pathya test</title>"
        html = {"Accept": "text/html"}
        assert client.get("/read/opaque-id", headers=html).status_code == 200
        assert client.get("/missing.js", headers=html).status_code == 404
        assert client.get("/.env", headers=html).status_code == 404
        assert client.get("/api/unknown", headers=html).status_code == 404
        assert client.get("/api/readyz").status_code == 200
        origin = {"Origin": "https://preview.test"}
        credentials = {"email": "preview@example.test", "password": "temporary synthetic password"}
        assert (
            client.post("/api/auth/register", headers=origin, json=credentials).status_code == 201
        )
        assert client.post("/api/auth/login", headers=origin, json=credentials).status_code == 200
        assert client.get("/api/auth/me").status_code == 200
        csrf = client.cookies["pathya_csrf"]
        assert (
            client.post("/api/auth/logout", headers={**origin, "X-CSRF-Token": csrf}).status_code
            == 204
        )


def test_page_image_returns_pdf_raster_normalized_crop_and_etag(upload_client):
    pytest.importorskip("pypdfium2")
    writer = PdfWriter()
    page = writer.add_blank_page(300, 400)
    stream = DecodedStreamObject()
    stream.set_data(b"1 0 0 rg 0 200 150 200 re f")
    page.replace_contents(stream)
    pdf = io.BytesIO()
    writer.write(pdf)
    document_id = upload(upload_client, pdf.getvalue()).json()["document_id"]
    fixture = json.loads(Path("tests/fixtures/chapter_demo.json").read_bytes())
    fixture.update(pages=fixture["pages"][:1], blocks=[], edges=[])
    database = upload_client.app.state.database
    import_extraction(database, document_id, fixture)
    path = f"/documents/{document_id}/pages/0/image"
    assert upload_client.get(path).status_code == 503
    upload_client.app.state.settings.pdf_preview_enabled = True
    response = upload_client.get(path, params={"bbox": "0,0,0.5,0.5"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(response.content)) as preview:
        assert preview.size == (450, 600)
        assert preview.convert("RGB").getpixel((225, 300)) == (255, 0, 0)
    unchanged = upload_client.get(
        path, params={"bbox": "0,0,0.5,0.5"}, headers={"If-None-Match": response.headers["etag"]}
    )
    assert unchanged.status_code == 304 and not unchanged.content
    assert upload_client.get(path, params={"bbox": "0,0,2,1"}).status_code == 422
