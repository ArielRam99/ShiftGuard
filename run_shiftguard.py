import os
import secrets
import threading
import webbrowser
from pathlib import Path

from waitress import serve

from shiftguard import create_app
from shiftguard.db import get_db, seed_demo_data


def _data_directory():
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return root / "ShiftGuard"


def _seed_empty_installation(app):
    with app.app_context():
        employee_count = get_db().execute(
            "SELECT COUNT(*) AS count FROM employees"
        ).fetchone()["count"]
        if employee_count == 0:
            seed_demo_data()


def main():
    data_directory = _data_directory()
    data_directory.mkdir(parents=True, exist_ok=True)

    host = "127.0.0.1"
    port = int(os.environ.get("SHIFTGUARD_PORT", "5000"))
    url = f"http://{host}:{port}"
    app = create_app(
        {"DATABASE": str(data_directory / "shiftguard.sqlite")}
    )
    _seed_empty_installation(app)
    with app.app_context():
        if get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone() is None:
            token = os.environ.get("SHIFTGUARD_SETUP_TOKEN") or secrets.token_urlsafe(32)
            if len(token) < 32 or not token.isascii():
                raise RuntimeError("Setup token must contain at least 32 ASCII characters")
            app.config["SETUP_TOKEN"] = token
            url = f"{url}/setup?token={token}"

    if os.environ.get("SHIFTGUARD_NO_BROWSER") != "1":
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    serve(app, host=host, port=port, threads=4)


if __name__ == "__main__":
    main()
