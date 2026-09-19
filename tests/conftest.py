import pytest
from werkzeug.security import generate_password_hash

from shiftguard import create_app
from shiftguard.db import get_db


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "shiftguard-test.sqlite"),
            "WTF_CSRF_ENABLED": False,
        }
    )
    with application.app_context():
        database = get_db()
        database.execute(
            """
            INSERT INTO users (email, display_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                "admin@example.com",
                "Test Administrator",
                generate_password_hash("test-password-123"),
                "admin",
            ),
        )
        database.commit()
    yield application


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    response = test_client.post(
        "/login",
        data={"email": "admin@example.com", "password": "test-password-123"},
    )
    assert response.status_code == 302
    return test_client


@pytest.fixture()
def anonymous_client(app):
    return app.test_client()

