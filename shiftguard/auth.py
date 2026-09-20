from functools import wraps
from urllib.parse import urljoin, urlparse

import click
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


bp = Blueprint("auth", __name__)
login_manager = LoginManager()
csrf = CSRFProtect()
ROLE_LEVELS = {"viewer": 0, "manager": 1, "admin": 2}


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.email = row["email"]
        self.display_name = row["display_name"]
        self.role = row["role"]
        self.active = bool(row["active"])

    @property
    def is_active(self):
        return self.active


@login_manager.user_loader
def load_user(user_id):
    if not user_id.isdigit():
        return None
    row = get_db().execute(
        "SELECT id, email, display_name, role, active FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    return User(row) if row is not None else None


def _safe_next_url(target):
    if not target:
        return None
    host = urlparse(request.host_url)
    destination = urlparse(urljoin(request.host_url, target))
    if destination.scheme in {"http", "https"} and destination.netloc == host.netloc:
        return destination.path + (f"?{destination.query}" if destination.query else "")
    return None


@bp.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone() is None:
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        row = get_db().execute(
            "SELECT * FROM users WHERE LOWER(email) = ?", (email,)
        ).fetchone()
        if row is not None and row["active"] and check_password_hash(
            row["password_hash"], password
        ):
            login_user(User(row))
            return redirect(_safe_next_url(request.args.get("next")) or url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@bp.route("/setup", methods=("GET", "POST"))
def setup():
    database = get_db()
    if database.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not email or "@" not in email:
            flash("Enter a valid email address.", "error")
        elif not display_name:
            flash("Enter your name.", "error")
        elif len(password) < 12:
            flash("Password must contain at least 12 characters.", "error")
        elif password != confirmation:
            flash("Passwords do not match.", "error")
        else:
            cursor = database.execute(
                """
                INSERT INTO users (email, display_name, password_hash, role)
                VALUES (?, ?, ?, 'admin')
                """,
                (email, display_name, generate_password_hash(password)),
            )
            database.commit()
            login_user(load_user(str(cursor.lastrowid)))
            return redirect(url_for("dashboard"))
    return render_template("setup.html")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def role_required(minimum_role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if ROLE_LEVELS.get(current_user.role, -1) < ROLE_LEVELS[minimum_role]:
                return {"error": "You do not have permission for this action"}, 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


@click.command("create-user")
@click.option("--email", prompt=True)
@click.option("--display-name", prompt=True)
@click.option(
    "--role",
    type=click.Choice(tuple(ROLE_LEVELS), case_sensitive=False),
    default="admin",
    show_default=True,
)
@click.password_option()
def create_user_command(email, display_name, role, password):
    """Create a ShiftGuard login account."""
    email = email.strip().lower()
    display_name = display_name.strip()
    if not email or "@" not in email:
        raise click.ClickException("Enter a valid email address.")
    if not display_name:
        raise click.ClickException("Display name cannot be empty.")
    if len(password) < 12:
        raise click.ClickException("Password must contain at least 12 characters.")
    try:
        get_db().execute(
            """
            INSERT INTO users (email, display_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (email, display_name, generate_password_hash(password), role.lower()),
        )
        get_db().commit()
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise click.ClickException("A user with that email already exists.") from error
        raise
    click.echo(f"Created {role.lower()} user {email}.")


def init_app(app):
    login_manager.login_view = "auth.login"

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return {"error": "Authentication required"}, 401
        return redirect(url_for("auth.login", next=request.full_path))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            return {"error": "CSRF token is missing or invalid"}, 400
        return render_template("login.html", csrf_error=error.description), 400

    login_manager.init_app(app)
    csrf.init_app(app)
    app.register_blueprint(bp)
    app.cli.add_command(create_user_command)