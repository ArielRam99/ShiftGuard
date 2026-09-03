import sqlite3
from datetime import date, datetime

from flask import Blueprint, jsonify, request, send_file

from .ai import SUPPORTED_MODELS, StaffingPredictor
from .db import get_db
from .reports import MIME_TYPES, analytics_report, schedule_report
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


def _integer(body, field, *, minimum=None, maximum=None, default=None):
    value = body.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise APIError(f"'{field}' must be a whole number")
    if minimum is not None and value < minimum:
        raise APIError(f"'{field}' must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise APIError(f"'{field}' must be at most {maximum}")
    return value


def _optional_text(body, field):
    value = body.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise APIError(f"'{field}' must be non-empty text")
    return value.strip()


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
        SELECT id, name, role, max_weekly_hours, hourly_rate, department,
               max_overtime_hours, minimum_rest_hours, max_consecutive_days,
               active, created_at
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
        SELECT id, employee_id, day_of_week, start_time, end_time, preference
        FROM availability WHERE id = ?
        """,
        (availability_id,),
    ).fetchone()
    if availability is None:
        raise APIError("Availability not found", 404)
    return availability


def _skill(database, skill_id):
    skill = database.execute(
        "SELECT id, name, created_at FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()
    if skill is None:
        raise APIError("Skill not found", 404)
    return skill


def _time_off_request(database, request_id):
    item = database.execute(
        """
        SELECT id, employee_id, start_date, end_date, reason, status,
               requested_at, decided_by, manager_note, decided_at
        FROM time_off_requests WHERE id = ?
        """,
        (request_id,),
    ).fetchone()
    if item is None:
        raise APIError("Time-off request not found", 404)
    return item


def _day_of_week(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise APIError("'day_of_week' must be an integer from 0 (Monday) to 6")
    if value < 0 or value > 6:
        raise APIError("'day_of_week' must be between 0 (Monday) and 6 (Sunday)")
    return value


def _preference(value):
    if value not in {"available", "preferred"}:
        raise APIError("'preference' must be available or preferred")
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
            "supported_strategies": ["auto", *SUPPORTED_MODELS],
        }
    )


@bp.get("/model/comparison")
def model_comparison():
    database = get_db()
    history = database.execute(
        """
        SELECT day_of_week, workload_score, shift_length_hours, required_staff
        FROM historical_staffing
        ORDER BY id
        """
    ).fetchall()
    comparison = StaffingPredictor().compare(history)
    comparison["metric_guidance"] = {
        "selection": "Lowest MAE, then lowest RMSE",
        "mae": "Mean absolute staffing error; lower is better",
        "rmse": "Root mean squared staffing error; lower is better",
        "r2": "Explained variance; higher is better",
    }
    return jsonify(comparison)


@bp.get("/employees")
def list_employees():
    database = get_db()

    filters = []
    parameters = []

    role = request.args.get("role")
    if role is not None:
        role = role.strip()
        if not role:
            raise APIError("'role' must not be empty")
        filters.append("LOWER(role) = LOWER(?)")
        parameters.append(role)

    department = request.args.get("department")
    if department is not None:
        department = department.strip()
        if not department:
            raise APIError("'department' must not be empty")
        filters.append("LOWER(department) = LOWER(?)")
        parameters.append(department)

    active = request.args.get("active")
    if active is not None:
        active = active.lower()
        if active not in {"true", "false"}:
            raise APIError("'active' must be true or false")
        filters.append("active = ?")
        parameters.append(1 if active == "true" else 0)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    employees = database.execute(
        f"""
        SELECT id, name, role, max_weekly_hours, hourly_rate, department,
               max_overtime_hours, minimum_rest_hours, max_consecutive_days,
               active, created_at
        FROM employees
        {where_clause}
        ORDER BY name
        """,
        parameters,
    ).fetchall()

    return jsonify({"employees": [dict(row) for row in employees]})


@bp.get("/employees/<int:employee_id>")
def get_employee(employee_id):
    database = get_db()
    return jsonify(dict(_employee(database, employee_id)))


@bp.post("/employees")
def create_employee():
    body = _json_body()
    name = _required_text(body, "name")
    role = _required_text(body, "role")
    max_hours = _number(
        body, "max_weekly_hours", minimum=1, maximum=168, default=40
    )
    hourly_rate = _number(body, "hourly_rate", minimum=0, default=0)
    department = _optional_text(body, "department") or "General"
    max_overtime_hours = _number(
        body, "max_overtime_hours", minimum=0, maximum=128, default=8
    )
    minimum_rest_hours = _number(
        body, "minimum_rest_hours", minimum=0, maximum=48, default=11
    )
    max_consecutive_days = _integer(
        body, "max_consecutive_days", minimum=1, maximum=31, default=6
    )

    database = get_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO employees (
                name, role, max_weekly_hours, hourly_rate, department,
                max_overtime_hours, minimum_rest_hours, max_consecutive_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                role,
                max_hours,
                hourly_rate,
                department,
                max_overtime_hours,
                minimum_rest_hours,
                max_consecutive_days,
            ),
        )
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("An employee with that name already exists", 409) from error

    return jsonify(dict(_employee(database, cursor.lastrowid))), 201


@bp.patch("/employees/<int:employee_id>")
def update_employee(employee_id):
    body = _json_body()
    supported_fields = {
        "name",
        "role",
        "max_weekly_hours",
        "hourly_rate",
        "department",
        "max_overtime_hours",
        "minimum_rest_hours",
        "max_consecutive_days",
        "active",
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
    if "department" in body:
        updates["department"] = _required_text(body, "department")
    if "max_overtime_hours" in body:
        updates["max_overtime_hours"] = _number(
            body, "max_overtime_hours", minimum=0, maximum=128
        )
    if "minimum_rest_hours" in body:
        updates["minimum_rest_hours"] = _number(
            body, "minimum_rest_hours", minimum=0, maximum=48
        )
    if "max_consecutive_days" in body:
        updates["max_consecutive_days"] = _integer(
            body, "max_consecutive_days", minimum=1, maximum=31
        )
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
        SELECT id, employee_id, day_of_week, start_time, end_time, preference
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
    preference = _preference(body.get("preference", "available"))
    if start_time >= end_time:
        raise APIError("'end_time' must be later than 'start_time'")

    database = get_db()
    _employee(database, employee_id)

    try:
        cursor = database.execute(
            """
            INSERT INTO availability
                (employee_id, day_of_week, start_time, end_time, preference)
            VALUES (?, ?, ?, ?, ?)
            """,
            (employee_id, day_of_week, start_time, end_time, preference),
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
                "preference": preference,
            }
        ),
        201,
    )


@bp.patch("/availability/<int:availability_id>")
def update_availability(availability_id):
    body = _json_body()
    supported_fields = {"day_of_week", "start_time", "end_time", "preference"}
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
    preference = (
        _preference(body["preference"])
        if "preference" in body
        else current["preference"]
    )
    if start_time >= end_time:
        raise APIError("'end_time' must be later than 'start_time'")

    try:
        database.execute(
            """
            UPDATE availability
            SET day_of_week = ?, start_time = ?, end_time = ?, preference = ?
            WHERE id = ?
            """,
            (day_of_week, start_time, end_time, preference, availability_id),
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


@bp.get("/skills")
def list_skills():
    rows = get_db().execute(
        "SELECT id, name, created_at FROM skills ORDER BY name"
    ).fetchall()
    return jsonify({"skills": [dict(row) for row in rows]})


@bp.post("/skills")
def create_skill():
    name = _required_text(_json_body(), "name")
    database = get_db()
    try:
        cursor = database.execute("INSERT INTO skills (name) VALUES (?)", (name,))
        database.commit()
    except sqlite3.IntegrityError as error:
        raise APIError("A skill with that name already exists", 409) from error
    return jsonify(dict(_skill(database, cursor.lastrowid))), 201


def _employee_skills(database, employee_id):
    return database.execute(
        """
        SELECT s.id, s.name, es.proficiency, es.created_at
        FROM employee_skills AS es
        JOIN skills AS s ON s.id = es.skill_id
        WHERE es.employee_id = ?
        ORDER BY s.name
        """,
        (employee_id,),
    ).fetchall()


@bp.get("/employees/<int:employee_id>/skills")
def list_employee_skills(employee_id):
    database = get_db()
    _employee(database, employee_id)
    return jsonify(
        {"skills": [dict(row) for row in _employee_skills(database, employee_id)]}
    )


@bp.post("/employees/<int:employee_id>/skills")
def assign_employee_skill(employee_id):
    body = _json_body()
    skill_name = _required_text(body, "skill_name")
    proficiency = _integer(
        body, "proficiency", minimum=1, maximum=5, default=3
    )
    database = get_db()
    _employee(database, employee_id)
    database.execute("INSERT OR IGNORE INTO skills (name) VALUES (?)", (skill_name,))
    skill = database.execute(
        "SELECT id, name FROM skills WHERE LOWER(name) = LOWER(?)", (skill_name,)
    ).fetchone()
    database.execute(
        """
        INSERT INTO employee_skills (employee_id, skill_id, proficiency)
        VALUES (?, ?, ?)
        ON CONFLICT(employee_id, skill_id)
        DO UPDATE SET proficiency = excluded.proficiency
        """,
        (employee_id, skill["id"], proficiency),
    )
    database.commit()
    assigned = database.execute(
        """
        SELECT s.id, s.name, es.proficiency, es.created_at
        FROM employee_skills AS es
        JOIN skills AS s ON s.id = es.skill_id
        WHERE es.employee_id = ? AND es.skill_id = ?
        """,
        (employee_id, skill["id"]),
    ).fetchone()
    return jsonify(dict(assigned)), 201


@bp.delete("/employees/<int:employee_id>/skills/<int:skill_id>")
def remove_employee_skill(employee_id, skill_id):
    database = get_db()
    _employee(database, employee_id)
    _skill(database, skill_id)
    cursor = database.execute(
        "DELETE FROM employee_skills WHERE employee_id = ? AND skill_id = ?",
        (employee_id, skill_id),
    )
    if cursor.rowcount == 0:
        raise APIError("Employee skill assignment not found", 404)
    database.commit()
    return "", 204


def _time_off_rows(database, *, employee_id=None, status=None):
    filters = []
    parameters = []
    if employee_id is not None:
        filters.append("tor.employee_id = ?")
        parameters.append(employee_id)
    if status is not None:
        filters.append("tor.status = ?")
        parameters.append(status)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    return database.execute(
        f"""
        SELECT tor.id, tor.employee_id, e.name AS employee_name,
               tor.start_date, tor.end_date, tor.reason, tor.status,
               tor.requested_at, tor.decided_by, tor.manager_note, tor.decided_at
        FROM time_off_requests AS tor
        JOIN employees AS e ON e.id = tor.employee_id
        {where_clause}
        ORDER BY tor.start_date, tor.id
        """,
        parameters,
    ).fetchall()


def _time_off_status(value):
    if value is None:
        return None
    value = value.lower()
    if value not in {"pending", "approved", "rejected"}:
        raise APIError("'status' must be pending, approved, or rejected")
    return value


@bp.get("/time-off")
def list_time_off():
    status = _time_off_status(request.args.get("status"))
    employee_id = request.args.get("employee_id")
    if employee_id is not None:
        try:
            employee_id = int(employee_id)
        except ValueError as error:
            raise APIError("'employee_id' must be a positive integer") from error
        if employee_id < 1:
            raise APIError("'employee_id' must be a positive integer")
    rows = _time_off_rows(get_db(), employee_id=employee_id, status=status)
    return jsonify({"time_off_requests": [dict(row) for row in rows]})


@bp.get("/employees/<int:employee_id>/time-off")
def list_employee_time_off(employee_id):
    database = get_db()
    _employee(database, employee_id)
    status = _time_off_status(request.args.get("status"))
    rows = _time_off_rows(database, employee_id=employee_id, status=status)
    return jsonify({"time_off_requests": [dict(row) for row in rows]})


@bp.post("/employees/<int:employee_id>/time-off")
def request_employee_time_off(employee_id):
    body = _json_body()
    start_date = _date_field(body.get("start_date"), "start_date")
    end_date = _date_field(body.get("end_date"), "end_date")
    if start_date > end_date:
        raise APIError("'start_date' must be on or before 'end_date'")
    reason = _optional_text(body, "reason")
    database = get_db()
    _employee(database, employee_id)
    overlap = database.execute(
        """
        SELECT id FROM time_off_requests
        WHERE employee_id = ?
          AND status IN ('pending', 'approved')
          AND start_date <= ? AND end_date >= ?
        LIMIT 1
        """,
        (employee_id, end_date.isoformat(), start_date.isoformat()),
    ).fetchone()
    if overlap is not None:
        raise APIError(
            "An active time-off request already overlaps those dates", 409
        )
    cursor = database.execute(
        """
        INSERT INTO time_off_requests
            (employee_id, start_date, end_date, reason)
        VALUES (?, ?, ?, ?)
        """,
        (employee_id, start_date.isoformat(), end_date.isoformat(), reason),
    )
    database.commit()
    return jsonify(dict(_time_off_request(database, cursor.lastrowid))), 201


@bp.patch("/time-off/<int:request_id>/decision")
def decide_time_off(request_id):
    body = _json_body()
    decision = _required_text(body, "decision").lower()
    if decision not in {"approved", "rejected"}:
        raise APIError("'decision' must be either 'approved' or 'rejected'")
    manager_name = _required_text(body, "manager_name")
    manager_note = body.get("manager_note")
    if manager_note is not None and not isinstance(manager_note, str):
        raise APIError("'manager_note' must be text")
    database = get_db()
    current = _time_off_request(database, request_id)
    if current["status"] != "pending":
        raise APIError("Only pending time-off requests can be decided", 409)
    cursor = database.execute(
        """
        UPDATE time_off_requests
        SET status = ?, decided_by = ?, manager_note = ?,
            decided_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'pending'
        """,
        (decision, manager_name, manager_note, request_id),
    )
    if cursor.rowcount == 0:
        database.rollback()
        raise APIError("Only pending time-off requests can be decided", 409)
    database.commit()
    return jsonify(dict(_time_off_request(database, request_id)))


def _filtered_shifts(database):
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

    required_department = request.args.get("required_department")
    if required_department is not None:
        required_department = required_department.strip()
        if not required_department:
            raise APIError("'required_department' must not be empty")
        filters.append("LOWER(s.required_department) = LOWER(?)")
        parameters.append(required_department)

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
    return [get_shift(database, row["id"]) for row in rows]


@bp.get("/shifts")
def list_shifts():
    return jsonify({"shifts": _filtered_shifts(get_db())})


def _report_format(file_format):
    if file_format not in MIME_TYPES:
        raise APIError("Report format must be pdf or xlsx", 404)
    return file_format


@bp.get("/reports/schedules.<file_format>")
def export_schedules(file_format):
    file_format = _report_format(file_format)
    report = schedule_report(_filtered_shifts(get_db()), file_format)
    return send_file(
        report,
        mimetype=MIME_TYPES[file_format],
        as_attachment=True,
        download_name=f"shiftguard-schedules.{file_format}",
    )


@bp.get("/reports/analytics.<file_format>")
def export_analytics(file_format):
    file_format = _report_format(file_format)
    database = get_db()
    shifts = _filtered_shifts(database)
    status_counts = {"draft": 0, "approved": 0, "rejected": 0}
    assignments = []
    for shift in shifts:
        status_counts[shift["status"]] += 1
        assignments.extend(shift["assignments"])
    summary = {
        "total_shifts": len(shifts),
        "draft_shifts": status_counts["draft"],
        "approved_shifts": status_counts["approved"],
        "rejected_shifts": status_counts["rejected"],
        "total_assignments": len(assignments),
        "projected_overtime_hours": round(
            sum(item["projected_overtime_hours"] for item in assignments), 2
        ),
    }
    history = database.execute(
        """
        SELECT day_of_week, workload_score, shift_length_hours, required_staff
        FROM historical_staffing
        ORDER BY id
        """
    ).fetchall()
    comparison = StaffingPredictor().compare(history)
    report = analytics_report(summary, comparison, file_format)
    return send_file(
        report,
        mimetype=MIME_TYPES[file_format],
        as_attachment=True,
        download_name=f"shiftguard-analytics.{file_format}",
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
    required_department = _optional_text(body, "required_department")
    required_skills = body.get("required_skills", [])
    if not isinstance(required_skills, list) or any(
        not isinstance(item, str) or not item.strip() for item in required_skills
    ):
        raise APIError("'required_skills' must be a list of non-empty skill names")
    required_skills = [item.strip() for item in required_skills]
    if len({item.casefold() for item in required_skills}) != len(required_skills):
        raise APIError("'required_skills' must not contain duplicates")
    if len(required_skills) > 20:
        raise APIError("'required_skills' must contain at most 20 skills")
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

    model_strategy = body.get("model_strategy", "random_forest")
    allowed_strategies = {"auto", *SUPPORTED_MODELS}
    if not isinstance(model_strategy, str) or model_strategy not in allowed_strategies:
        raise APIError(
            "'model_strategy' must be auto, random_forest, "
            "gradient_boosting, or linear_regression"
        )

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
        model_strategy=model_strategy,
        required_department=required_department,
        required_skills=required_skills,
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
