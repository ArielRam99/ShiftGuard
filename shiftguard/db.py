import sqlite3
from pathlib import Path

import click
from flask import current_app, g


SCHEMA_FILE = Path(__file__).with_name("schema.sql")

DEFAULT_ROLES = (
    "Accountant",
    "Administrative Assistant",
    "Assistant",
    "Billing Specialist",
    "Care Coordinator",
    "Cashier",
    "Case Manager",
    "Clinical Assistant",
    "Clinical Manager",
    "Customer Service Representative",
    "Data Analyst",
    "Dietitian",
    "Dispatcher",
    "Emergency Medical Technician",
    "Facilities Coordinator",
    "Finance Manager",
    "Human Resources Specialist",
    "IT Support Specialist",
    "Laboratory Technician",
    "Licensed Practical Nurse",
    "Maintenance Technician",
    "Medical Assistant",
    "Medical Records Specialist",
    "Nurse",
    "Nurse Practitioner",
    "Occupational Therapist",
    "Operations Manager",
    "Paramedic",
    "Patient Care Technician",
    "Pharmacist",
    "Pharmacy Technician",
    "Physical Therapist",
    "Physician",
    "Physician Assistant",
    "Radiologic Technologist",
    "Receptionist",
    "Registered Nurse",
    "Respiratory Therapist",
    "Scheduler",
    "Security Officer",
    "Social Worker",
    "Sonographer",
    "Sterile Processing Technician",
    "Supervisor",
    "Surgical Technologist",
    "Transporter",
    "Unit Clerk",
    "Warehouse Associate",
    "Workforce Analyst",
    "X-Ray Technician",
)

DEFAULT_DEPARTMENTS = (
    "Administration",
    "Clinical",
    "Emergency",
    "Facilities",
    "Finance",
    "General",
    "Human Resources",
    "Information Technology",
    "Laboratory",
    "Operations",
    "Pharmacy",
    "Radiology",
    "Surgery",
)


def get_db():
    """Return one SQLite connection per Flask request/app context."""
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    database = get_db()
    database.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    _migrate_existing_database(database)
    _seed_reference_catalogs(database)
    database.commit()


def _migrate_existing_database(database):
    """Apply additive SQLite migrations needed by existing local databases."""
    def add_columns(table, additions):
        columns = {
            row["name"]
            for row in database.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if not columns:
            return
        for column, definition in additions.items():
            if column not in columns:
                database.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )

    add_columns(
        "employees",
        {
            "department": "TEXT NOT NULL DEFAULT 'General' COLLATE NOCASE",
            "max_overtime_hours": (
                "REAL NOT NULL DEFAULT 8 "
                "CHECK (max_overtime_hours >= 0 AND max_overtime_hours <= 128)"
            ),
            "minimum_rest_hours": (
                "REAL NOT NULL DEFAULT 11 "
                "CHECK (minimum_rest_hours >= 0 AND minimum_rest_hours <= 48)"
            ),
            "max_consecutive_days": (
                "INTEGER NOT NULL DEFAULT 6 "
                "CHECK (max_consecutive_days BETWEEN 1 AND 31)"
            ),
        },
    )
    add_columns(
        "availability",
        {
            "preference": (
                "TEXT NOT NULL DEFAULT 'available' "
                "CHECK (preference IN ('available', 'preferred'))"
            )
        },
    )
    add_columns(
        "shifts",
        {
            "staffing_range_min": "INTEGER",
            "staffing_range_max": "INTEGER",
            "confidence_level": "REAL",
            "model_mae": "REAL",
            "required_department": "TEXT COLLATE NOCASE",
            "constraint_summary": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    shift_columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(shifts)").fetchall()
    }
    if {"required_staff", "staffing_range_min", "staffing_range_max"}.issubset(
        shift_columns
    ):
        database.execute(
            """
            UPDATE shifts
            SET staffing_range_min = COALESCE(staffing_range_min, required_staff),
                staffing_range_max = COALESCE(staffing_range_max, required_staff),
                constraint_summary = COALESCE(constraint_summary, '{}')
            """
        )


def _seed_reference_catalogs(database):
    database.executemany(
        "INSERT OR IGNORE INTO roles (name) VALUES (?)",
        [(name,) for name in DEFAULT_ROLES],
    )
    database.executemany(
        "INSERT OR IGNORE INTO departments (name) VALUES (?)",
        [(name,) for name in DEFAULT_DEPARTMENTS],
    )
    database.execute(
        """
        INSERT OR IGNORE INTO roles (name)
        SELECT DISTINCT role FROM employees WHERE TRIM(role) <> ''
        """
    )
    database.execute(
        """
        INSERT OR IGNORE INTO departments (name)
        SELECT DISTINCT department FROM employees WHERE TRIM(department) <> ''
        """
    )


def seed_demo_data():
    """Insert deterministic, non-sensitive demo data without duplicating it."""
    database = get_db()
    employees = [
        ("Jordan Lee", "Nurse", 40, 32, "Clinical"),
        ("Casey Smith", "Nurse", 36, 30, "Clinical"),
        ("Taylor Kim", "Nurse", 32, 34, "Clinical"),
        ("Morgan Diaz", "Assistant", 40, 22, "Clinical"),
    ]
    database.executemany(
        """
        INSERT OR IGNORE INTO employees
            (name, role, max_weekly_hours, hourly_rate, department)
        VALUES (?, ?, ?, ?, ?)
        """,
        employees,
    )

    employee_ids = [
        row["id"] for row in database.execute("SELECT id FROM employees").fetchall()
    ]
    availability_rows = [
        (employee_id, day, "06:00", "22:00")
        for employee_id in employee_ids
        for day in range(7)
    ]
    database.executemany(
        """
        INSERT OR IGNORE INTO availability
            (employee_id, day_of_week, start_time, end_time)
        VALUES (?, ?, ?, ?)
        """,
        availability_rows,
    )

    database.executemany(
        "INSERT OR IGNORE INTO skills (name) VALUES (?)",
        [("Patient Care",), ("Medication Administration",), ("Triage",)],
    )
    nurse_ids = [
        row["id"]
        for row in database.execute(
            "SELECT id FROM employees WHERE LOWER(role) = 'nurse'"
        ).fetchall()
    ]
    patient_care = database.execute(
        "SELECT id FROM skills WHERE LOWER(name) = 'patient care'"
    ).fetchone()["id"]
    database.executemany(
        """
        INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency)
        VALUES (?, ?, 3)
        """,
        [(employee_id, patient_care) for employee_id in nurse_ids],
    )

    history_rows = []
    for day in range(7):
        history_rows.extend(
            [
                (day, 20, 8, 1),
                (day, 40, 8, 2),
                (day, 60, 8, 2),
                (day, 80, 8, 3),
                (day, 95, 8, 4),
            ]
        )
    database.executemany(
        """
        INSERT OR IGNORE INTO historical_staffing
            (day_of_week, workload_score, shift_length_hours, required_staff)
        VALUES (?, ?, ?, ?)
        """,
        history_rows,
    )
    database.commit()


@click.command("init-db")
def init_db_command():
    """Create the database tables."""
    init_db()
    click.echo("Initialized the ShiftGuard database.")


@click.command("seed-demo")
def seed_demo_command():
    """Load safe demo employees, availability, and historical demand."""
    seed_demo_data()
    click.echo("Loaded ShiftGuard demo data.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
