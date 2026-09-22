import re

import pytest

from shiftguard import create_app
from shiftguard.db import get_db


@pytest.fixture()
def setup_app(tmp_path):
    return create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "DATABASE": str(tmp_path / "setup.sqlite"),
        "SETUP_TOKEN": "private-setup-token-with-at-least-32-characters",
    })


def _csrf(response):
    return re.search(
        rb'name="csrf_token" value="([^"]+)"', response.data
    ).group(1).decode()


def _account_data(**tokens):
    return {
        "display_name": "First Administrator",
        "email": "first@example.com",
        "password": "first-password-123",
        "password_confirmation": "first-password-123",
        **tokens,
    }


def _assert_token_private(response, token):
    for item in (*response.history, response):
        assert token.encode() not in item.data
        assert all(token not in value for _, value in item.headers)


@pytest.mark.parametrize("path", ["/login", "/", "/api/health"])
def test_public_pages_do_not_disclose_setup_token(setup_app, path):
    client = setup_app.test_client()
    response = client.get(path, follow_redirects=True)
    assert response.status_code == 200
    _assert_token_private(response, setup_app.config["SETUP_TOKEN"])
    with client.session_transaction() as session:
        assert setup_app.config["SETUP_TOKEN"] not in repr(dict(session))


def test_anonymous_login_post_does_not_disclose_setup_token(setup_app):
    client = setup_app.test_client()
    csrf_token = _csrf(client.get("/login", follow_redirects=True))
    response = client.post("/login", data={
        "csrf_token": csrf_token, "email": "unknown@example.com", "password": "wrong",
    })
    assert response.status_code == 200
    _assert_token_private(response, setup_app.config["SETUP_TOKEN"])


@pytest.mark.parametrize("supplied", ["", "incorrect"])
def test_public_csrf_token_does_not_authorize_setup(setup_app, supplied):
    client = setup_app.test_client()
    csrf_token = _csrf(client.get("/login", follow_redirects=True))
    page = client.get("/setup", query_string={"token": supplied})
    assert page.status_code == 403
    response = client.post(
        "/setup", data=_account_data(csrf_token=csrf_token, setup_token=supplied)
    )
    assert response.status_code == 403
    _assert_token_private(response, setup_app.config["SETUP_TOKEN"])
    with setup_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_private_setup_requires_csrf_and_closes_after_first_account(setup_app):
    client = setup_app.test_client()
    token = setup_app.config["SETUP_TOKEN"]
    page = client.get("/setup", query_string={"token": token})
    assert page.status_code == 200
    csrf_token = _csrf(page)
    assert client.post("/setup", data=_account_data(setup_token=token)).status_code == 400
    created = client.post(
        "/setup", data=_account_data(csrf_token=csrf_token, setup_token=token)
    )
    assert created.status_code == 302
    assert client.get("/").status_code == 200

    outsider = setup_app.test_client()
    csrf_token = _csrf(outsider.get("/login"))
    closed = outsider.post(
        "/setup", data=_account_data(csrf_token=csrf_token, setup_token=token)
    )
    assert closed.status_code == 302
    assert closed.headers["Location"].endswith("/login")
    with setup_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
