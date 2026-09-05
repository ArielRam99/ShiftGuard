from pathlib import Path

from flask import Flask, render_template, send_from_directory

from . import api, db


def create_app(test_config=None):
    """Create and configure the ShiftGuard Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "shiftguard.sqlite"),
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(api.bp)
    api.register_error_handlers(app)

    # The schema uses CREATE TABLE IF NOT EXISTS, so startup is safe and
    # first-time users do not need a separate migration step for this MVP.
    with app.app_context():
        db.init_db()

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/sample-data.csv")
    def sample_data():
        return send_from_directory(
            Path(app.root_path).parent / "sample_data",
            "sample_shifts_year.csv",
            as_attachment=True,
        )

    return app

