import sqlite3
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from .db import get_db
from .scheduling import generate_shift_recommendation, get_shift


bp = Blueprint("api", __name__, url_prefix="/api")


class APIError(Exception):
    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(error):
        response = {"error": error.message}
        if error.details:
            response["details"] = error.details
        return jsonify(response), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": "Resource not found"}), 404


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object")
    return body


def _required_text(body, field):
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise APIError(f"'{field}' is required and must be text")
    return value.strip()


def _number(body, field, *, minimum=None, maximum=None, default=None):
    value = body.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise APIError(f"'{field}' must be a number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise APIError(f"'{field}' must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise APIError(f"'{field}' must be at most {maximum}")
    return value


def _time(value, field):
    if not isinstance(value, str):
        raise APIError(f"'{field}' must use HH:MM format")
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as error:
        raise APIError(f"'{field}' must use 24-hour HH:MM format") from error
    return parsed.strftime("%H:%M")


def _date(value):
    if not isinstance(value, str):
        raise APIError("'shift_date' must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise APIError("'shift_date' must be a valid YYYY-MM-DD date") from error


@bp.get("/health")
def health():
    database = get_db()
    database.execute("SELECT 1").fetchone()
    return jsonify({"service": "ShiftGuard AI", "status": "ok"})


@bp.get("/model/status")
def model_status():
    database = get_db()
    count = database.execute(
        "SELECT COUNT(*) AS count FROM historical_staffing"
    ).fetchone()["count"]
    return jsonify(
        {
            "training_records": count,
            "strategy": "random_forest" if count >= 5 else "rules_fallback",
            "advisory_only": True,
        }
    )


@bp.get("/employees")
def list_employees():
    database = get_db()
    employees = database.execute(
        """
        SELECT id, name, role, max_weekly_hours, hourly_rate, active, created_at
        FROM employees
        ORDER BY name
        """
    ).fetchall()
    return jsonify({"employees": [dict(row) for row in employees]})


@bp.post("/employees")
def create_employee():
    body = _json_body()
    name = _required_text(body, "name")
    role = _required_text(body, "role")
    max_hours = _number(
        body, "max_weekly_hours", minimum=1, maximum=168, default=40
    )
    hourly_rate = _number(body, "hourly_rate", minimum=0, default=0)

    database = get_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO employees (name, role, max_weekly_hours, hourly_rate)
            VALUES (?, ?, ?, ?)
            """,
            (name, role, max_hours, hourly_rate),
        )
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("An employee with that name already exists", 409) from error

    employee = database.execute(
        """
        SELECT id, name, role, max_weekly_hours, hourly_rate, active, created_at
        FROM employees WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(dict(employee)), 201


@bp.post("/employees/<int:employee_id>/availability")
def add_availability(employee_id):
    body = _json_body()
    day_of_week = body.get("day_of_week")
    if isinstance(day_of_week, bool) or not isinstance(day_of_week, int):
        raise APIError("'day_of_week' must be an integer from 0 (Monday) to 6")
    if day_of_week < 0 or day_of_week > 6:
        raise APIError("'day_of_week' must be between 0 (Monday) and 6 (Sunday)")

    start_time = _time(body.get("start_time"), "start_time")
    end_time = _time(body.get("end_time"), "end_time")
    if start_time >= end_time:
        raise APIError("'end_time' must be later than 'start_time'")

    database = get_db()
    if database.execute(
        "SELECT id FROM employees WHERE id = ?", (employee_id,)
    ).fetchone() is None:
        raise APIError("Employee not found", 404)

    try:
        cursor = database.execute(
            """
            INSERT INTO availability
                (employee_id, day_of_week, start_time, end_time)
            VALUES (?, ?, ?, ?)
            """,
            (employee_id, day_of_week, start_time, end_time),
        )
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("That availability record already exists", 409) from error

    return (
        jsonify(
            {
                "id": cursor.lastrowid,
                "employee_id": employee_id,
                "day_of_week": day_of_week,
                "start_time": start_time,
                "end_time": end_time,
            }
        ),
        201,
    )


@bp.post("/shifts/recommendations")
def recommend_shift():
    body = _json_body()
    shift_date = _date(body.get("shift_date"))
    start_time = _time(body.get("start_time"), "start_time")
    end_time = _time(body.get("end_time"), "end_time")
    if start_time >= end_time:
        raise APIError("Overnight shifts are not supported in this MVP")

    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    duration_hours = (end - start).total_seconds() / 3600
    required_role = _required_text(body, "required_role")
    workload_score = _number(
        body, "workload_score", minimum=0, maximum=100
    )

    required_staff = body.get("required_staff")
    if required_staff is not None:
        if isinstance(required_staff, bool) or not isinstance(required_staff, int):
            raise APIError("'required_staff' must be a whole number")
        if required_staff < 1 or required_staff > 50:
            raise APIError("'required_staff' must be between 1 and 50")

    allow_overtime = body.get("allow_overtime", False)
    if not isinstance(allow_overtime, bool):
        raise APIError("'allow_overtime' must be true or false")

    recommendation = generate_shift_recommendation(
        get_db(),
        shift_date=shift_date,
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration_hours,
        required_role=required_role,
        workload_score=workload_score,
        required_staff_override=required_staff,
        allow_overtime=allow_overtime,
    )
    return jsonify(recommendation), 201


@bp.get("/shifts/<int:shift_id>")
def fetch_shift(shift_id):
    shift = get_shift(get_db(), shift_id)
    if shift is None:
        raise APIError("Shift not found", 404)
    return jsonify(shift)


@bp.patch("/shifts/<int:shift_id>/decision")
def decide_shift(shift_id):
    body = _json_body()
    decision = _required_text(body, "decision").lower()
    if decision not in {"approved", "rejected"}:
        raise APIError("'decision' must be either 'approved' or 'rejected'")
    manager_name = _required_text(body, "manager_name")
    manager_note = body.get("manager_note")
    if manager_note is not None and not isinstance(manager_note, str):
        raise APIError("'manager_note' must be text")

    database = get_db()
    current = database.execute(
        "SELECT status FROM shifts WHERE id = ?", (shift_id,)
    ).fetchone()
    if current is None:
        raise APIError("Shift not found", 404)
    if current["status"] != "draft":
        raise APIError("Only draft recommendations can be decided", 409)

    database.execute(
        """
        UPDATE shifts
        SET status = ?, decided_by = ?, manager_note = ?,
            decided_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (decision, manager_name, manager_note, shift_id),
    )
    database.execute(
        "UPDATE shift_assignments SET status = ? WHERE shift_id = ?",
        (decision, shift_id),
    )
    database.commit()
    return jsonify(get_shift(database, shift_id))

