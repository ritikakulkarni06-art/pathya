import json

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.repos import sessions, users
from app.main import create_app
from app.services.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    LoginLimiter,
    csrf_token,
    current_user,
    require_doc_access,
    token_digest,
)


@pytest.fixture
def session_app(seeded):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=seeded.path.parent,
        pathya_db_path=seeded.path,
        auth_mode="session",
        session_secret="s" * 48,
    )
    with seeded.write_tx() as connection:
        for user_id, role in [
            ("other", "user"),
            ("reader", "user"),
            ("reviewer", "user"),
            ("admin", "admin"),
        ]:
            users.create(connection, user_id, user_id + "@example.test", None, "now")
            connection.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        for user_id, role in [("reader", "reader"), ("reviewer", "reviewer")]:
            connection.execute(
                "INSERT INTO document_grants VALUES ('d',?,?, 'u','now')", (user_id, role)
            )
        for user_id in ["u", "other", "reader", "reviewer", "admin"]:
            sessions.create(
                connection,
                user_id,
                user_id,
                token_digest(user_id + "-token"),
                "2026-01-01",
                "2099-01-01",
            )
    return create_app(settings)


def signed_client(application, user_id):
    client = TestClient(application, base_url="https://testserver")
    if user_id:
        token = user_id + "-token"
        csrf = csrf_token(token, application.state.settings)
        client.cookies.set(SESSION_COOKIE, token)
        client.cookies.set(CSRF_COOKIE, csrf)
        client.headers["X-CSRF-Token"] = csrf
    return client


@pytest.mark.parametrize("user_id", [None, "other", "reader", "reviewer", "u", "admin"])
def test_registered_protected_route_matrix(session_app, user_id):
    with signed_client(session_app, user_id) as client:
        authenticated = user_id is not None
        expected_grants = (
            401
            if not authenticated
            else 204
            if user_id == "u"
            else 403
            if user_id in {"reader", "reviewer"}
            else 404
        )
        assert client.get("/auth/me").status_code == (200 if authenticated else 401)
        assert (
            client.post(
                "/documents/d/grants", json={"user_id": "reader", "role": "reader"}
            ).status_code
            == expected_grants
        )
        assert client.delete("/documents/d/grants/reader").status_code == expected_grants
        assert client.post("/auth/logout").status_code == (204 if authenticated else 401)
        if authenticated:
            assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("minimum", ["reader", "reviewer", "owner"])
@pytest.mark.parametrize("user_id", [None, "other", "reader", "reviewer", "u", "admin"])
def test_access_dependency_matrix(session_app, minimum, user_id):
    @session_app.get("/documents/{document_id}/probe")
    def probe(document=Depends(require_doc_access(minimum))):
        return {"id": document["id"]}

    with signed_client(session_app, user_id) as client:
        rank = {"reader": 1, "reviewer": 2, "u": 3}
        expected = (
            401
            if user_id is None
            else 404
            if user_id not in rank
            else 200
            if rank[user_id] >= {"reader": 1, "reviewer": 2, "owner": 3}[minimum]
            else 403
        )
        assert client.get("/documents/d/probe").status_code == expected
        if user_id:
            assert client.get("/documents/nonexistent/probe").status_code == 404


def test_route_enumeration_requires_authentication(tmp_path):
    application = create_app(Settings(_env_file=None, pathya_env="test", pathya_data_dir=tmp_path))
    public = {"/healthz", "/readyz", "/auth/register", "/auth/login"}

    def dependencies(node):
        for dependency in node.dependencies:
            yield dependency.call
            yield from dependencies(dependency)

    checked = []

    def leaf_routes(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            else:
                nested = getattr(route, "original_router", None)
                assert nested is not None, "Unexpected unaudited route type"
                yield from leaf_routes(nested.routes)

    resolved = list(leaf_routes(application.routes))
    assert {route.path for route in resolved} == set(application.openapi()["paths"])
    for route in resolved:
        if route.path not in public:
            assert current_user in list(dependencies(route.dependant)), route.path
            checked.append(route.path)
    assert set(checked) >= {
        "/auth/me",
        "/auth/logout",
        "/documents/{document_id}/grants",
        "/documents/{document_id}/grants/{user_id}",
    }


def test_real_registration_login_csrf_logout(tmp_path, caplog):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path,
        auth_mode="session",
        session_secret="secret" * 8,
        login_rate_limit=20,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        credentials = {"email": "Student@example.test", "password": "Long enough password 12"}
        created = client.post("/auth/register", json=credentials)
        assert created.status_code == 201
        assert created.json()["email"] == "student@example.test"
        assert "password" not in json.dumps(created.json())
        response = client.post("/auth/login", json=credentials)
        assert response.status_code == 200
        assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
        assert all(
            "Secure" in cookie and "SameSite=lax" in cookie
            for cookie in response.headers.get_list("set-cookie")
        )
        raw_token = client.cookies[SESSION_COOKIE]
        with client.app.state.database.read_conn() as conn:
            row = conn.execute("SELECT * FROM sessions").fetchone()
            assert row["token_hash"] == token_digest(raw_token)
            assert raw_token not in str(row)
            account = users.by_email(conn, "student@example.test")
            assert account["password_hash"].startswith("$argon2id$")
        assert client.post("/auth/logout").status_code == 403
        client.headers["X-CSRF-Token"] = "forged"
        client.cookies.set(CSRF_COOKIE, "forged")
        assert client.post("/auth/logout").status_code == 403
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, raw_token)
        csrf = csrf_token(raw_token, settings)
        client.cookies.set(CSRF_COOKIE, csrf)
        client.headers["X-CSRF-Token"] = csrf
        assert client.post("/auth/logout").status_code == 204
        assert client.get("/auth/me").status_code == 401
    assert credentials["password"] not in caplog.text
    assert raw_token not in caplog.text


def test_expired_revoked_and_forged_sessions(session_app):
    with session_app.state.database.write_tx() as conn:
        conn.execute("UPDATE sessions SET expires_at='2000-01-01' WHERE id='reader'")
        conn.execute("UPDATE sessions SET revoked_at='2026-01-01' WHERE id='reviewer'")
    for user_id in ["reader", "reviewer", "forged"]:
        with signed_client(session_app, user_id) as client:
            assert client.get("/auth/me").status_code == 401


def test_login_errors_limits_and_validation(tmp_path):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path,
        auth_mode="session",
        session_secret="s" * 40,
        login_rate_limit=2,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert (
            client.post(
                "/auth/register", json={"email": "invalid", "password": "short"}
            ).status_code
            == 422
        )
        payload = {"email": "missing@example.test", "password": "wrong password value"}
        assert client.post("/auth/login", json=payload).status_code == 401
        assert client.post("/auth/login", json=payload).status_code == 401
        assert client.post("/auth/login", json=payload).status_code == 429
        assert (
            client.post(
                "/auth/register", json=payload, headers={"Origin": "https://attacker.invalid"}
            ).status_code
            == 403
        )


def test_local_identity_still_checks_owner(tmp_path):
    with TestClient(
        create_app(Settings(_env_file=None, pathya_env="test", pathya_data_dir=tmp_path))
    ) as client:
        assert client.get("/auth/me").json()["email"] == "local@pathya.invalid"
        assert (
            client.post(
                "/documents/missing/grants", json={"user_id": "x", "role": "reader"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/auth/login", json={"email": "u@example.test", "password": "password 123456"}
            ).json()["code"]
            == "session_mode_required"
        )


def test_limiter_expires(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("app.services.auth.time.monotonic", lambda: clock[0])
    limiter = LoginLimiter(1, 10)
    limiter.check("ip", "email")
    clock[0] = 21.0
    limiter.check("ip", "email")
