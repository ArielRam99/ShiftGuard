import io
import json
import logging
from logging.handlers import RotatingFileHandler

from werkzeug.security import generate_password_hash

from shiftguard import create_app
from shiftguard.audit import init_app
from shiftguard.db import get_db


def capture(app):
    stream = io.StringIO()
    app.extensions["audit_logger"].addHandler(logging.StreamHandler(stream))
    return stream


def records(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_login_and_logout_record_actor_without_credentials(app, anonymous_client):
    with app.app_context():
        cursor = get_db().execute(
            """INSERT INTO users (email, display_name, password_hash, role)
               VALUES (?, ?, ?, 'manager')""",
            ("manager@example.com", "Manager", generate_password_hash("Never-Log-Password-42!")),
        )
        get_db().commit()
        user_id = cursor.lastrowid
    stream = capture(app)
    assert anonymous_client.post(
        "/login", data={"email": "manager@example.com", "password": "Never-Log-Password-42!"}
    ).status_code == 302
    assert anonymous_client.post("/logout").status_code == 302
    events = records(stream)
    assert [(event["event"], event["actor_id"]) for event in events] == [
        ("auth.login", user_id), ("auth.logout", user_id)
    ]
    for secret in ("Never-Log", "manager@example.com", "Manager"):
        assert secret not in stream.getvalue()


def test_decision_records_ids_and_authenticated_name(app, client):
    employee_id = client.post(
        "/api/employees", json={"name": "Private Employee", "role": "Nurse"}
    ).get_json()["id"]
    request_id = client.post(
        f"/api/employees/{employee_id}/time-off",
        json={"start_date": "2026-11-01", "end_date": "2026-11-02", "reason": "Private reason"},
    ).get_json()["id"]
    stream = capture(app)
    result = client.patch(
        f"/api/time-off/{request_id}/decision",
        json={"decision": "approved", "manager_note": "Private note", "manager_name": "Forged"},
    )
    assert result.status_code == 200
    event = records(stream)[0]
    assert event["resource_ids"] == {"request_id": request_id}
    assert event["decision"] == "approved"
    assert event["result"] == {"id": request_id}
    for secret in ("Private", "Forged", "Test Administrator"):
        assert secret not in stream.getvalue()


def test_denials_and_unknown_paths_do_not_log_request_input(app, anonymous_client):
    stream = capture(app)
    assert anonymous_client.get("/api/employees?password=secret-query").status_code == 401
    assert anonymous_client.get("/secret-path?token=private-token").status_code == 404
    events = records(stream)
    assert [event["status"] for event in events] == [401, 404]
    assert events[1]["event"] == "unmatched"
    for secret in ("secret-query", "private-token", "secret-path"):
        assert secret not in stream.getvalue()


def test_setup_log_does_not_contain_private_token(tmp_path):
    token = "private-setup-token-with-at-least-32-characters"
    app = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False,
        "DATABASE": str(tmp_path / "setup.sqlite"), "SETUP_TOKEN": token,
    })
    stream = capture(app)
    assert app.test_client().get(f"/setup?token={token}").status_code == 200
    assert token not in stream.getvalue()


def test_unexpected_errors_return_generic_json_and_are_audited(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/test-failure")
    def fail():
        raise RuntimeError("Private failure details")

    stream = capture(app)
    response = app.test_client().get("/test-failure")
    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}
    assert records(stream)[0]["status"] == 500
    assert "Private failure details" not in stream.getvalue()


def test_logging_is_isolated_rotating_and_not_duplicated(tmp_path):
    applications = []
    try:
        for name in ("one", "two"):
            directory = tmp_path / name
            directory.mkdir()
            app = create_app({"DATABASE": str(directory / "data.sqlite")})
            applications.append(app)
            init_app(app)
            handlers = [
                handler for handler in app.extensions["audit_logger"].handlers
                if isinstance(handler, RotatingFileHandler)
            ]
            assert len(handlers) == 1
            assert handlers[0].baseFilename == str(directory / "logs" / "shiftguard.log")
        applications[0].test_client().get("/missing-one")
        assert "unmatched" in (tmp_path / "one/logs/shiftguard.log").read_text()
        assert (tmp_path / "two/logs/shiftguard.log").read_text() == ""
    finally:
        for app in applications:
            for handler in app.extensions["audit_logger"].handlers:
                handler.close()


def test_testing_mode_does_not_open_runtime_log(app):
    assert not any(
        isinstance(handler, RotatingFileHandler)
        for handler in app.extensions["audit_logger"].handlers
    )
