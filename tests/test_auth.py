import re
from datetime import timedelta

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from shiftguard import create_app
from shiftguard.db import get_db


def _add_user(app, email, role):
    with app.app_context():
        database = get_db()
        database.execute(
            """
            INSERT INTO users (email, display_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (email, "Read Only User", generate_password_hash("viewer-password-123"), role),
        )
        database.commit()


def test_anonymous_requests_are_challenged(anonymous_client):
    dashboard = anonymous_client.get("/")
    assert dashboard.status_code == 302
    assert "/login" in dashboard.headers["Location"]

    api = anonymous_client.get("/api/employees")
    assert api.status_code == 401
    assert api.get_json()["error"] == "Authentication required"
    assert anonymous_client.get("/api/health").status_code == 200


def test_first_run_creates_one_administrator(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "DATABASE": str(tmp_path / "first-run.sqlite"),
        }
    )
    first_run = application.test_client()
    assert first_run.get("/login").headers["Location"].endswith("/setup")

    created = first_run.post(
        "/setup",
        data={
            "display_name": "First Administrator",
            "email": "first@example.com",
            "password": "first-password-123",
            "password_confirmation": "first-password-123",
        },
    )
    assert created.status_code == 302
    assert first_run.get("/").status_code == 200
    assert first_run.get("/setup").headers["Location"].endswith("/login")

    with application.app_context():
        user = get_db().execute("SELECT role, password_hash FROM users").fetchone()
    assert user["role"] == "admin"
    assert check_password_hash(user["password_hash"], "first-password-123")


def test_login_uses_hashed_password_and_logout(app, anonymous_client):
    with app.app_context():
        stored = get_db().execute(
            "SELECT password_hash FROM users WHERE email = 'admin@example.com'"
        ).fetchone()["password_hash"]
    assert stored != "test-password-123"
    assert check_password_hash(stored, "test-password-123")

    rejected = anonymous_client.post(
        "/login", data={"email": "admin@example.com", "password": "wrong"}
    )
    assert rejected.status_code == 200
    assert b"Invalid email or password" in rejected.data

    logged_in = anonymous_client.post(
        "/login",
        data={"email": "admin@example.com", "password": "test-password-123"},
    )
    assert logged_in.status_code == 302
    assert logged_in.headers["Location"].endswith("/")
    assert anonymous_client.get("/").status_code == 200

    assert anonymous_client.post("/logout").status_code == 302
    assert anonymous_client.get("/api/employees").status_code == 401


def test_login_is_permanent_for_eight_hours(app, anonymous_client):
    anonymous_client.post(
        "/login",
        data={"email": "admin@example.com", "password": "test-password-123"},
    )
    with anonymous_client.session_transaction() as browser_session:
        assert browser_session.permanent is True
    assert app.permanent_session_lifetime == timedelta(hours=8)


def test_deactivated_account_loses_existing_session(app, anonymous_client):
    anonymous_client.post(
        "/login",
        data={"email": "admin@example.com", "password": "test-password-123"},
    )
    with app.app_context():
        get_db().execute(
            "UPDATE users SET active = 0 WHERE email = 'admin@example.com'"
        )
        get_db().commit()
    assert anonymous_client.get("/api/employees").status_code == 401


def test_short_configured_secret_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIFTGUARD_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="at least 32"):
        create_app({"TESTING": True, "DATABASE": str(tmp_path / "secret.sqlite")})


def test_viewer_can_read_but_cannot_mutate(app):
    _add_user(app, "viewer@example.com", "viewer")
    viewer = app.test_client()
    viewer.post(
        "/login",
        data={"email": "viewer@example.com", "password": "viewer-password-123"},
    )

    assert viewer.get("/api/employees").status_code == 200
    forbidden = viewer.post("/api/roles", json={"name": "Forbidden Role"})
    assert forbidden.status_code == 403


def test_api_mutations_require_csrf_token(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    dashboard = client.get("/")
    token = re.search(
        rb'<meta name="csrf-token" content="([^"]+)">', dashboard.data
    ).group(1).decode()

    missing = client.post("/api/roles", json={"name": "CSRF Role"})
    assert missing.status_code == 400
    accepted = client.post(
        "/api/roles",
        json={"name": "CSRF Role"},
        headers={"X-CSRFToken": token},
    )
    assert accepted.status_code == 201
