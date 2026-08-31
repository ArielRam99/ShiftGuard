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
    return _date_field(value, "shift_date")


def _date_field(value, field):
    if not isinstance(value, str):
        raise APIError(f"'{field}' must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise APIError(f"'{field}' must be a valid YYYY-MM-DD date") from error


def _employee(database, employee_id):
    employee = database.execute(
        """
        SELECT id, name, role, max_weekly_hours, hourly_rate, active, created_at
        FROM employees WHERE id = ?
        """,
        (employee_id,),
    ).fetchone()
    if employee is None:
        raise APIError("Employee not found", 404)
    return employee


def _availability(database, availability_id):
    availability = database.execute(
        """
        SELECT id, employee_id, day_of_week, start_time, end_time
        FROM availability WHERE id = ?
        """,
        (availability_id,),
    ).fetchone()
    if availability is None:
        raise APIError("Availability not found", 404)
    return availability


def _day_of_week(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise APIError("'day_of_week' must be an integer from 0 (Monday) to 6")
    if value < 0 or value > 6:
        raise APIError("'day_of_week' must be between 0 (Monday) and 6 (Sunday)")
    return value


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


@bp.patch("/employees/<int:employee_id>")
def update_employee(employee_id):
    body = _json_body()
    supported_fields = {
        "name", "role", "max_weekly_hours", "hourly_rate", "active"
    }
    unknown_fields = set(body) - supported_fields
    if unknown_fields:
        raise APIError(
            "Unsupported employee fields",
            details={"fields": sorted(unknown_fields)},
        )
    if not supported_fields.intersection(body):
        raise APIError("At least one employee field must be provided")

    database = get_db()
    _employee(database, employee_id)
    updates = {}
    if "name" in body:
        updates["name"] = _required_text(body, "name")
    if "role" in body:
        updates["role"] = _required_text(body, "role")
    if "max_weekly_hours" in body:
        updates["max_weekly_hours"] = _number(
            body, "max_weekly_hours", minimum=1, maximum=168
        )
    if "hourly_rate" in body:
        updates["hourly_rate"] = _number(body, "hourly_rate", minimum=0)
    if "active" in body:
        if not isinstance(body["active"], bool):
            raise APIError("'active' must be true or false")
        updates["active"] = int(body["active"])

    assignments = ", ".join(f"{field} = ?" for field in updates)
    try:
        database.execute(
            f"UPDATE employees SET {assignments} WHERE id = ?",
            [*updates.values(), employee_id],
        )
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("An employee with that name already exists", 409) from error
    return jsonify(dict(_employee(database, employee_id)))


@bp.get("/employees/<int:employee_id>/availability")
def list_employee_availability(employee_id):
    database = get_db()
    _employee(database, employee_id)
    availability = database.execute(
        """
        SELECT id, employee_id, day_of_week, start_time, end_time
        FROM availability
        WHERE employee_id = ?
        ORDER BY day_of_week, start_time, end_time, id
        """,
        (employee_id,),
    ).fetchall()
    return jsonify({"availability": [dict(row) for row in availability]})


@bp.post("/employees/<int:employee_id>/availability")
def add_availability(employee_id):
    body = _json_body()
    day_of_week = _day_of_week(body.get("day_of_week"))

    start_time = _time(body.get("start_time"), "start_time")
    end_time = _time(body.get("end_time"), "end_time")
    if start_time >= end_time:
        raise APIError("'end_time' must be later than 'start_time'")

    database = get_db()
    _employee(database, employee_id)

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


@bp.patch("/availability/<int:availability_id>")
def update_availability(availability_id):
    body = _json_body()
    supported_fields = {"day_of_week", "start_time", "end_time"}
    unknown_fields = set(body) - supported_fields
    if unknown_fields:
        raise APIError(
            "Unsupported availability fields",
            details={"fields": sorted(unknown_fields)},
        )
    if not supported_fields.intersection(body):
        raise APIError("At least one availability field must be provided")

    database = get_db()
    current = _availability(database, availability_id)
    day_of_week = (
        _day_of_week(body["day_of_week"])
        if "day_of_week" in body
        else current["day_of_week"]
    )
    start_time = (
        _time(body["start_time"], "start_time")
        if "start_time" in body
        else current["start_time"]
    )
    end_time = (
        _time(body["end_time"], "end_time")
        if "end_time" in body
        else current["end_time"]
    )
    if start_time >= end_time:
        raise APIError("'end_time' must be later than 'start_time'")

    try:
        database.execute(
            """
            UPDATE availability
            SET day_of_week = ?, start_time = ?, end_time = ?
            WHERE id = ?
            """,
            (day_of_week, start_time, end_time, availability_id),
        )
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("That availability record already exists", 409) from error
    return jsonify(dict(_availability(database, availability_id)))


@bp.delete("/availability/<int:availability_id>")
def delete_availability(availability_id):
    database = get_db()
    _availability(database, availability_id)
    database.execute("DELETE FROM availability WHERE id = ?", (availability_id,))
    database.commit()
    return "", 204


@bp.get("/shifts")
def list_shifts():
    filters = []
    parameters = []

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if date_from is not None:
        parsed_from = _date_field(date_from, "date_from")
        filters.append("s.shift_date >= ?")
        parameters.append(parsed_from.isoformat())
    else:
        parsed_from = None
    if date_to is not None:
        parsed_to = _date_field(date_to, "date_to")
        filters.append("s.shift_date <= ?")
        parameters.append(parsed_to.isoformat())
    else:
        parsed_to = None
    if (
        parsed_from is not None
        and parsed_to is not None
        and parsed_from > parsed_to
    ):
        raise APIError("'date_from' must be on or before 'date_to'")

    required_role = request.args.get("required_role")
    if required_role is not None:
        required_role = required_role.strip()
        if not required_role:
            raise APIError("'required_role' must not be empty")
        filters.append("LOWER(s.required_role) = LOWER(?)")
        parameters.append(required_role)

    status = request.args.get("status")
    if status is not None:
        status = status.lower()
        if status not in {"draft", "approved", "rejected"}:
            raise APIError("'status' must be draft, approved, or rejected")
        filters.append("s.status = ?")
        parameters.append(status)

    employee_id = request.args.get("employee_id")
    join = ""
    if employee_id is not None:
        try:
            employee_id = int(employee_id)
        except ValueError as error:
            raise APIError("'employee_id' must be a positive integer") from error
        if employee_id < 1:
            raise APIError("'employee_id' must be a positive integer")
        join = "JOIN shift_assignments AS filter_sa ON filter_sa.shift_id = s.id"
        filters.append("filter_sa.employee_id = ?")
        parameters.append(employee_id)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    database = get_db()
    rows = database.execute(
        f"""
        SELECT DISTINCT s.id
        FROM shifts AS s
        {join}
        {where_clause}
        ORDER BY s.shift_date, s.start_time, s.id
        """,
        parameters,
    ).fetchall()
    return jsonify({"shifts": [get_shift(database, row["id"]) for row in rows]})


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
