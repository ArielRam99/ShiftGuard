import sqlite3

from shiftguard.db import DEFAULT_ROLES, _migrate_existing_database, seed_demo_data


def test_existing_database_receives_additive_phase_b_columns(tmp_path):
    database = sqlite3.connect(tmp_path / "legacy.sqlite")
    database.row_factory = sqlite3.Row
    database.execute(
        """
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            max_weekly_hours REAL NOT NULL,
            hourly_rate REAL NOT NULL,
            active INTEGER NOT NULL,
            created_at TEXT
        )
        """
    )
    database.execute(
        """
        CREATE TABLE availability (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        )
        """
    )
    database.execute(
        """
        CREATE TABLE shifts (
            id INTEGER PRIMARY KEY,
            required_staff INTEGER NOT NULL
        )
        """
    )
    database.execute("INSERT INTO shifts (id, required_staff) VALUES (1, 6)")
    database.execute(
        """
        INSERT INTO employees
            (id, name, role, max_weekly_hours, hourly_rate, active)
        VALUES (1, 'Legacy Employee', 'Nurse', 40, 30, 1)
        """
    )
    database.execute(
        """
        INSERT INTO availability
            (id, employee_id, day_of_week, start_time, end_time)
        VALUES (1, 1, 1, '08:00', '17:00')
        """
    )

    _migrate_existing_database(database)

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(shifts)")
    }
    assert {
        "staffing_range_min",
        "staffing_range_max",
        "confidence_level",
        "model_mae",
        "required_department",
        "constraint_summary",
    }.issubset(columns)
    migrated = database.execute(
        "SELECT staffing_range_min, staffing_range_max FROM shifts WHERE id = 1"
    ).fetchone()
    assert dict(migrated) == {
        "staffing_range_min": 6,
        "staffing_range_max": 6,
    }
    employee = database.execute(
        """
        SELECT department, max_overtime_hours, minimum_rest_hours,
               max_consecutive_days
        FROM employees WHERE id = 1
        """
    ).fetchone()
    assert dict(employee) == {
        "department": "General",
        "max_overtime_hours": 8,
        "minimum_rest_hours": 11,
        "max_consecutive_days": 6,
    }
    availability = database.execute(
        "SELECT preference FROM availability WHERE id = 1"
    ).fetchone()
    assert availability["preference"] == "available"


def test_fresh_database_has_phase_b_tables(app):
    from shiftguard.db import get_db

    with app.app_context():
        database = get_db()
        tables = {
            row["name"]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "roles",
        "departments",
        "skills",
        "employee_skills",
        "time_off_requests",
    }.issubset(tables)

    with app.app_context():
        roles = get_db().execute("SELECT name FROM roles").fetchall()
        departments = get_db().execute("SELECT name FROM departments").fetchall()
    assert len(roles) == 50
    assert {row["name"] for row in departments} >= {
        "Clinical",
        "Emergency",
        "General",
        "Surgery",
    }


def test_demo_seed_creates_200_employees_across_predefined_roles(app):
    from shiftguard.db import get_db

    with app.app_context():
        database = get_db()
        cursor = database.execute(
            """
            INSERT INTO employees
                (name, role, max_weekly_hours, hourly_rate, department)
            VALUES ('Existing User', 'Nurse', 40, 30, 'Clinical')
            """
        )
        existing_employee_id = cursor.lastrowid
        database.executemany(
            """
            INSERT INTO employees
                (name, role, max_weekly_hours, hourly_rate, department)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("Jordan Lee", "Nurse", 40, 32, "Clinical"),
                ("Casey Smith", "Nurse", 36, 30, "Clinical"),
                ("Taylor Kim", "Nurse", 32, 34, "Clinical"),
                ("Morgan Diaz", "Assistant", 40, 22, "Clinical"),
            ],
        )
        database.commit()

        seed_demo_data()
        seed_demo_data()

        employee_count = database.execute(
            "SELECT COUNT(*) AS count FROM employees"
        ).fetchone()["count"]
        role_counts = database.execute(
            """
            SELECT role, COUNT(*) AS count
            FROM employees
            WHERE name <> 'Existing User'
            GROUP BY role
            """
        ).fetchall()
        invalid_roles = database.execute(
            """
            SELECT COUNT(*) AS count
            FROM employees AS e
            LEFT JOIN roles AS r ON LOWER(r.name) = LOWER(e.role)
            WHERE r.id IS NULL
            """
        ).fetchone()["count"]
        existing_availability = database.execute(
            "SELECT COUNT(*) AS count FROM availability WHERE employee_id = ?",
            (existing_employee_id,),
        ).fetchone()["count"]

    assert employee_count == 201
    assert {row["role"] for row in role_counts} == set(DEFAULT_ROLES)
    assert {row["count"] for row in role_counts} == {4}
    assert invalid_roles == 0
    assert existing_availability == 0
