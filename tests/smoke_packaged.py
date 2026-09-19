"""Exercise the real source server or Windows executable with disposable data."""
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def smoke(command):
    with tempfile.TemporaryDirectory(prefix="shiftguard-smoke-") as temporary:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        setup_token = secrets.token_urlsafe(32)
        password = secrets.token_urlsafe(24)
        environment = {
            **os.environ, "LOCALAPPDATA": temporary,
            "SHIFTGUARD_NO_BROWSER": "1", "SHIFTGUARD_PORT": str(port),
            "SHIFTGUARD_SETUP_TOKEN": setup_token,
            "SHIFTGUARD_SECURE_COOKIES": "0",
        }
        process = subprocess.Popen(
            command, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        base = f"http://127.0.0.1:{port}"
        csrf = None

        def request(path, body=None, method="GET", content_type="application/json"):
            data = json.dumps(body).encode() if isinstance(body, dict) else body
            headers = {"Content-Type": content_type}
            if csrf and content_type != "application/x-www-form-urlencoded":
                headers["X-CSRFToken"] = csrf
            with opener.open(
                Request(base + path, data=data, method=method, headers=headers),
                timeout=30,
            ) as response:
                raw = response.read()
                value = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
                return response.status, value

        def token_from(page, field=b'csrf-token" content="'):
            match = re.search(field + b'([^"<]+)', page)
            if match is None:
                match = re.search(rb'name="csrf_token" value="([^"]+)', page)
            if match is None:
                raise AssertionError("CSRF token was not rendered")
            return match.group(1).decode()

        def rejected(path, expected, **kwargs):
            try:
                request(path, **kwargs)
            except HTTPError as error:
                assert error.code == expected, (path, error.code, expected)
            else:
                raise AssertionError(f"{path} should have been rejected")

        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Application exited before startup completed")
                try:
                    assert request("/api/health")[1]["status"] == "ok"
                    break
                except URLError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Application did not become healthy")

            rejected("/api/employees", 401)
            setup_page = request(f"/setup?token={setup_token}")[1]
            setup_csrf = token_from(setup_page)
            setup_body = urlencode({
                "csrf_token": setup_csrf, "setup_token": setup_token,
                "display_name": "Smoke Administrator", "email": "smoke@example.com",
                "password": password, "password_confirmation": password,
            }).encode()
            assert request(
                "/setup", setup_body, "POST", "application/x-www-form-urlencoded"
            )[0] == 200

            page = request("/")[1]
            csrf = token_from(page)
            logout = urlencode({"csrf_token": csrf}).encode()
            assert request(
                "/logout", logout, "POST", "application/x-www-form-urlencoded"
            )[0] == 200
            login_page = request("/login")[1]
            login_body = urlencode({
                "csrf_token": token_from(login_page),
                "email": "smoke@example.com", "password": password,
            }).encode()
            dashboard = request(
                "/login", login_body, "POST", "application/x-www-form-urlencoded"
            )[1]
            csrf = token_from(dashboard)

            saved_csrf, csrf = csrf, None
            rejected("/api/shifts/recommendations", 400, body={}, method="POST")
            csrf = saved_csrf
            boundary = "ShiftGuardSmokeBoundary"
            csv = request("/sample-data.csv")[1]
            multipart = (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.csv\"\r\nContent-Type: text/csv\r\n\r\n".encode()
                + csv + f"\r\n--{boundary}--\r\n".encode()
            )
            imported = request(
                "/api/historical-staffing/import", multipart, "POST",
                f"multipart/form-data; boundary={boundary}",
            )[1]
            assert imported["total_rows"] > 0
            assert len(request("/api/model/comparison")[1]["models"]) == 3
            draft = request("/api/shifts/recommendations", {
                "shift_date": "2026-10-06", "start_time": "09:00",
                "end_time": "17:00", "required_role": "Nurse",
                "workload_score": 40, "model_strategy": "auto",
            }, "POST")[1]
            decision = request(
                f"/api/shifts/{draft['id']}/decision",
                {"decision": "approved", "manager_name": "Forged"}, "PATCH",
            )[1]
            assert decision["decided_by"] == "Smoke Administrator"
            for extension, prefix in (("pdf", b"%PDF"), ("xlsx", b"PK")):
                assert request(f"/api/reports/schedules.{extension}")[1].startswith(prefix)
            assert request(
                "/logout", urlencode({"csrf_token": csrf}).encode(), "POST",
                "application/x-www-form-urlencoded",
            )[0] == 200
            rejected("/api/employees", 401)
            print("Authenticated smoke test passed: setup, login, CSV, AI, approval, exports, logout.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Provide the application executable or source command")
    smoke(sys.argv[1:])
