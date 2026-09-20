import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from shiftguard import create_app
from shiftguard.db import get_db, init_db


def _pr8_database(path):
    """Freeze the pre-C2b account schema, rather than reusing today's schema."""
    with sqlite3.connect(path) as database:
        database.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer'
                    CHECK (role IN ('viewer', 'manager', 'admin')),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL, max_weekly_hours REAL NOT NULL,
                hourly_rate REAL NOT NULL, active INTEGER NOT NULL,
                created_at TEXT
            );
            INSERT INTO employees VALUES
                (7, 'Existing Employee', 'Nurse', 40, 30, 1, '2026-09-01');
            """
        )
        database.execute(
            """INSERT INTO users
               (id, email, display_name, password_hash, role, created_at)
               VALUES (41, 'existing@example.com', 'Existing Admin', ?,
                       'admin', '2026-09-01')""",
            (generate_password_hash("existing-password-123"),),
        )
        database.row_factory = sqlite3.Row
        return dict(database.execute("SELECT * FROM users").fetchone())


def test_pr8_database_upgrade_preserves_accounts_and_login(tmp_path):
    path = tmp_path / "pr8.sqlite"
    original = _pr8_database(path)
    app = create_app(
        {"TESTING": True, "DATABASE": str(path), "WTF_CSRF_ENABLED": False}
    )

    with app.app_context():
        database = get_db()
        assert dict(database.execute("SELECT * FROM users").fetchone()) == {
            **original, "employee_id": None,
        }
        employee = database.execute("SELECT * FROM employees WHERE id = 7").fetchone()
        assert (employee["name"], employee["hourly_rate"]) == ("Existing Employee", 30)
        database.execute("UPDATE users SET employee_id = 7 WHERE id = 41")
        database.commit()
        init_db()
        init_db()
        assert dict(database.execute("SELECT * FROM users").fetchone()) == {
            **original, "employee_id": 7,
        }
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []

    client = app.test_client()
    response = client.post(
        "/login",
        data={"email": original["email"], "password": "existing-password-123"},
    )
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    # A subsequent request exercises the session user loader as well as login.
    assert client.get("/api/employees").status_code == 200


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "pr8-upgrade"])
def test_employee_link_constraints_match_fresh_database(tmp_path, legacy):
    path = tmp_path / "accounts.sqlite"
    if legacy:
        _pr8_database(path)
    app = create_app({"TESTING": True, "DATABASE": str(path)})
    with app.app_context():
        database = get_db()
        employee_id = database.execute(
            """INSERT INTO employees
               (name, role, max_weekly_hours, hourly_rate, active)
               VALUES ('Linked Employee', 'Nurse', 40, 30, 1)"""
        ).lastrowid
        for number in (1, 2):
            database.execute(
                """INSERT INTO users (email, display_name, password_hash)
                   VALUES (?, 'Viewer', 'not-used-for-login')""",
                (f"viewer{number}@example.com",),
            )
        database.execute(
            "UPDATE users SET employee_id = ? WHERE email = 'viewer1@example.com'",
            (employee_id,),
        )
        database.commit()
        init_db()
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            database.execute(
                "UPDATE users SET employee_id = ? WHERE email = 'viewer2@example.com'",
                (employee_id,),
            )
        database.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            database.execute(
                "UPDATE users SET employee_id = 99999 WHERE email = 'viewer2@example.com'"
            )
        database.rollback()
        assert database.execute(
            "SELECT employee_id FROM users WHERE email = 'viewer2@example.com'"
        ).fetchone()["employee_id"] is None
