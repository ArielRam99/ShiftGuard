from shiftguard import create_app
from shiftguard.db import get_db
from run_shiftguard import _seed_empty_installation


def test_packaged_launcher_seeds_only_an_empty_installation(tmp_path):
    application = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "packaged.sqlite")}
    )

    _seed_empty_installation(application)
    with application.app_context():
        database = get_db()
        assert database.execute(
            "SELECT COUNT(*) AS count FROM employees"
        ).fetchone()["count"] == 200
        database.execute(
            "INSERT INTO employees (name, role) VALUES ('User Record', 'Nurse')"
        )
        database.commit()

    _seed_empty_installation(application)
    with application.app_context():
        database = get_db()
        assert database.execute(
            "SELECT COUNT(*) AS count FROM employees"
        ).fetchone()["count"] == 201