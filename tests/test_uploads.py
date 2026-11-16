import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from app.config import Settings
from app.main import create_app
from app.services.auth import current_user


def pdf_bytes(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(300, 400)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_bytes(size=(10, 10), exif=False):
    image = Image.new("RGB", size, "blue")
    output = io.BytesIO()
    metadata = Image.Exif()
    if exif:
        metadata[0x010E] = "Private camera metadata"
    image.save(output, format="PNG", exif=metadata)
    return output.getvalue()


@pytest.fixture
def upload_client(tmp_path):
    with TestClient(
        create_app(
            Settings(
                _env_file=None,
                pathya_env="test",
                pathya_data_dir=tmp_path,
                storage_min_free_bytes=0,
                max_upload_mb=1,
                max_pages=2,
                max_pixels=10000,
            )
        )
    ) as client:
        yield client


def upload(client, data, name="chapter.pdf", rights="Original synthetic content"):
    fields = {"title": "Synthetic chapter", "languages": "en,hi"}
    if rights is not None:
        fields["rights_note"] = rights
    return client.post(
        "/documents", data=fields, files={"file": (name, data, "application/octet-stream")}
    )


def test_upload_queues_once_and_metadata_is_private(upload_client):
    first = upload(upload_client, pdf_bytes())
    assert first.status_code == 202
    identifiers = first.json()
    duplicate = upload(upload_client, pdf_bytes())
    assert duplicate.status_code == 200
    assert duplicate.json()["document_id"] == identifiers["document_id"]
    assert duplicate.json()["job_id"] == identifiers["job_id"]
    document = upload_client.get("/documents/" + identifiers["document_id"])
    assert document.status_code == 200
    assert document.json()["state"] == "queued"
    assert len(upload_client.get("/documents").json()["documents"]) == 1
    with upload_client.app.state.database.read_conn() as conn:
        source = conn.execute("SELECT * FROM assets").fetchone()
        assert source["kind"] == "source"
        assert conn.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"] == 1
    assert "private_path" not in document.text
    upload_client.app.dependency_overrides[current_user] = lambda: {
        "id": "other",
        "role": "admin",
        "email": "other@example.test",
    }
    assert upload_client.get("/documents/" + identifiers["document_id"]).status_code == 404
    assert upload_client.get("/documents").json()["documents"] == []


@pytest.mark.parametrize(
    "data,name,rights,code",
    [
        (b"not a document", "chapter.pdf", "synthetic", "unsupported_type"),
        (b"%PDF-invalid", "chapter.pdf", "synthetic", "malformed"),
        (pdf_bytes(password="secret"), "chapter.pdf", "synthetic", "password_protected"),
        (pdf_bytes(3), "chapter.pdf", "synthetic", "too_many_pages"),
        (image_bytes(), "spoofed.pdf", "synthetic", "unsupported_type"),
        (image_bytes((1000, 1000)), "huge.png", "synthetic", "too_many_pixels"),
        (b"%PDF-" + b"x" * (1024 * 1024), "big.pdf", "synthetic", "too_large"),
        (pdf_bytes(), "chapter.pdf", None, "rights_note_required"),
        (pdf_bytes(), "chapter.pdf", "   ", "rights_note_required"),
    ],
)
def test_rejections_create_no_document_job_or_source(upload_client, data, name, rights, code):
    response = upload(upload_client, data, name, rights)
    assert response.status_code >= 400
    assert response.json()["code"] == code
    with upload_client.app.state.database.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM assets").fetchone()["n"] == 0
    assert not list(upload_client.app.state.settings.pathya_data_dir.glob("sources/**/*"))


def test_image_working_copy_has_no_exif_and_source_unchanged(upload_client):
    original = image_bytes(exif=True)
    response = upload(upload_client, original, "chapter.png")
    assert response.status_code == 202
    root = upload_client.app.state.settings.pathya_data_dir
    with upload_client.app.state.database.read_conn() as conn:
        assets = conn.execute("SELECT * FROM assets ORDER BY kind").fetchall()
    source = next(asset for asset in assets if asset["kind"] == "source")
    assert (root / source["private_path"]).read_bytes() == original
    derived = next(asset for asset in assets if asset["kind"] == "crop")
    with Image.open(root / derived["private_path"]) as image:
        assert not image.getexif()


def test_storage_full_creates_no_job(upload_client):
    upload_client.app.state.settings.storage_min_free_bytes = 10**30
    response = upload(upload_client, pdf_bytes())
    assert response.status_code == 507
    assert response.json()["code"] == "storage_full"
    assert upload_client.get("/documents").json()["documents"] == []


def test_body_limit_applies_before_multipart_processing(upload_client):
    response = upload_client.post(
        "/documents",
        content=b"x" * (2 * 1024 * 1024),
        headers={"Content-Type": "multipart/form-data; boundary=demo"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"


def test_receive_limit_cannot_be_bypassed_by_false_content_length(upload_client):
    boundary = "synthetic-boundary"
    body = (
        (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="file"; filename="large.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
        ).encode()
        + b"x" * (2 * 1024 * 1024)
        + ("\r\n--" + boundary + "--\r\n").encode()
    )
    response = upload_client.post(
        "/documents",
        content=body,
        headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": "1",
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
