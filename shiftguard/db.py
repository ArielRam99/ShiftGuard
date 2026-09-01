import sqlite3
from pathlib import Path

import click
from flask import current_app, g


SCHEMA_FILE = Path(__file__).with_name("schema.sql")


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
    database.commit()


def _migrate_existing_database(database):
    """Apply additive SQLite migrations needed by existing local databases."""
    shift_columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(shifts)").fetchall()
    }
    additions = {
        "staffing_range_min": "INTEGER",
        "staffing_range_max": "INTEGER",
        "confidence_level": "REAL",
        "model_mae": "REAL",
    }
    for column, definition in additions.items():
        if column not in shift_columns:
            database.execute(
                f"ALTER TABLE shifts ADD COLUMN {column} {definition}"
            )
    database.execute(
        """
        UPDATE shifts
        SET staffing_range_min = COALESCE(staffing_range_min, required_staff),
            staffing_range_max = COALESCE(staffing_range_max, required_staff)
        """
    )


def seed_demo_data():
    """Insert deterministic, non-sensitive demo data without duplicating it."""
    database = get_db()
    employees = [
        ("Jordan Lee", "Nurse", 40, 32),
        ("Casey Smith", "Nurse", 36, 30),
        ("Taylor Kim", "Nurse", 32, 34),
        ("Morgan Diaz", "Assistant", 40, 22),
    ]
    database.executemany(
        """
        INSERT OR IGNORE INTO employees
            (name, role, max_weekly_hours, hourly_rate)
        VALUES (?, ?, ?, ?)
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

