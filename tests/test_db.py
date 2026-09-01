import sqlite3

from shiftguard.db import _migrate_existing_database


def test_existing_shift_database_receives_forecast_columns(tmp_path):
    database = sqlite3.connect(tmp_path / "legacy.sqlite")
    database.row_factory = sqlite3.Row
    database.execute(
        """
        CREATE TABLE shifts (
            id INTEGER PRIMARY KEY,
            required_staff INTEGER NOT NULL
        )
        """
    )
    database.execute("INSERT INTO shifts (id, required_staff) VALUES (1, 6)")

    _migrate_existing_database(database)

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(shifts)")
    }
    assert {
        "staffing_range_min",
        "staffing_range_max",
        "confidence_level",
        "model_mae",
    }.issubset(columns)
    migrated = database.execute(
        "SELECT staffing_range_min, staffing_range_max FROM shifts WHERE id = 1"
    ).fetchone()
    assert dict(migrated) == {
        "staffing_range_min": 6,
        "staffing_range_max": 6,
    }
