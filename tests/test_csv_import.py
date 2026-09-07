from io import BytesIO

from shiftguard.db import get_db


VALID_CSV = b"""date,day_of_week,workload_hours,actual_headcount
2026-09-07,0,42.5,6
2026-09-08,1,55,8
"""


def _upload(client, content=VALID_CSV, filename="staffing.csv"):
    return client.post(
        "/api/historical-staffing/import",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def test_import_historical_staffing_csv_is_idempotent(client):
    response = _upload(client)

    assert response.status_code == 200
    assert response.get_json() == {
        "imported_records": 2,
        "skipped_duplicates": 0,
        "total_rows": 2,
    }

    duplicate = _upload(client)
    assert duplicate.status_code == 200
    assert duplicate.get_json()["skipped_duplicates"] == 2


def test_import_rejects_invalid_csv_atomically(app, client):
    response = _upload(
        client,
        b"""date,day_of_week,workload_hours,actual_headcount
2026-09-07,0,42.5,6
2026-09-08,4,55,8
""",
    )

    assert response.status_code == 400
    assert response.get_json()["details"]["invalid_count"] == 1
    with app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) AS count FROM historical_staffing"
        ).fetchone()["count"]
    assert count == 0


def test_import_requires_expected_columns(client):
    response = _upload(client, b"day,workload\nMonday,40\n")

    assert response.status_code == 400
    assert "CSV columns" in response.get_json()["error"]