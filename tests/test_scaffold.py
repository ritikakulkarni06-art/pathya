import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.logging import log_event, scrub
from app.main import create_app


@pytest.mark.parametrize(
    "values",
    [
        {"max_pages": 0},
        {"auth_mode": "session"},
        {"pathya_env": "prod"},
        {"cors_origins": ["*"]},
        {"llm_enabled": True},
        {"embeddings_enabled": True},
    ],
)
def test_invalid_config(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_log_scrubbing(caplog):
    caplog.set_level(logging.INFO, logger="pathya")
    log_event(
        route="/questions",
        status=200,
        text="SOURCE",
        nested={"question": "QUESTION", "safe": 1},
        api_key="KEY",
        items=[{"password": "PASSWORD", "token": "TOKEN"}],
    )
    event = json.loads(caplog.records[-1].message)
    assert event == {"route": "/questions", "status": 200, "nested": {"safe": 1}, "items": [{}]}
    assert scrub({"Authorization": "SECRET", "session_token": "SECRET"}) == {}


def test_health_ready_and_error(tmp_path, caplog):
    settings = Settings(_env_file=None, pathya_env="test", pathya_data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").status_code == 200
        response = client.get("/unknown?question=private-question")
        assert response.status_code == 404
        assert set(response.json()) == {"type", "title", "status", "detail", "code"}
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.headers["X-Request-ID"]
    assert "private-question" not in caplog.text
