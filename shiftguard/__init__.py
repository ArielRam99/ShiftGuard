import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required

from . import access, api, auth, db
from .logging_config import configure_logging


def _secret_key(instance_path):
    configured = os.environ.get("SHIFTGUARD_SECRET_KEY")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("SHIFTGUARD_SECRET_KEY must contain at least 32 characters")
        return configured
    secret_file = Path(instance_path) / ".secret-key"
    if not secret_file.exists():
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secrets.token_hex(32), encoding="ascii")
    secret = secret_file.read_text(encoding="ascii").strip()
    if len(secret) < 32:
        raise RuntimeError("Stored session secret must contain at least 32 characters")
    return secret


def create_app(test_config=None):
    """Create and configure the ShiftGuard Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "shiftguard.sqlite"),
        JSON_SORT_KEYS=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SECRET_KEY=_secret_key(app.instance_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SHIFTGUARD_SECURE_COOKIES") == "1",
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    configure_logging(app)

    db.init_app(app)
    auth.init_app(app)
    app.register_blueprint(api.bp)
    api.register_error_handlers(app)

    # The schema uses CREATE TABLE IF NOT EXISTS, so startup is safe and
    # first-time users do not need a separate migration step for this MVP.
    with app.app_context():
        db.init_db()

    @app.get("/")
    @login_required
    def dashboard():
        if current_user.role == "viewer":
            return redirect(url_for("my_shifts_page"))
        return render_template("dashboard.html")

    @app.get("/my-shifts")
    @login_required
    def my_shifts_page():
        if current_user.role != "viewer":
            return redirect(url_for("dashboard"))
        if access.linked_employee_id() is None:
            abort(403)
        return render_template("employee.html", shifts=access.assigned_shifts())

    @app.get("/sample-data.csv")
    @login_required
    def sample_data():
        return send_from_directory(
            Path(app.root_path).parent / "sample_data",
            "sample_shifts_year.csv",
            as_attachment=True,
        )

    return app
