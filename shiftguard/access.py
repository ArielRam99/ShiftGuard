"""Fail-closed API permissions and viewer ownership checks."""
from flask import jsonify, request
from flask_login import current_user

from .db import get_db


ADMIN_ONLY = {
    "create_role", "set_role_active", "create_department",
    "set_department_active", "import_historical_staffing",
}
VIEWER_OWN = {
    "get_employee", "list_employee_availability", "add_availability",
    "list_employee_skills", "list_employee_time_off", "request_employee_time_off",
}
AVAILABILITY_OWN = {"update_availability", "delete_availability"}
MANAGER_ACCESS = VIEWER_OWN | AVAILABILITY_OWN | {
    "list_roles", "list_departments", "model_status", "model_comparison",
    "list_employees", "create_employee", "update_employee", "list_skills",
    "create_skill", "assign_employee_skill", "remove_employee_skill",
    "list_time_off", "decide_time_off", "list_shifts", "export_schedules",
    "export_analytics", "recommend_shift", "fetch_shift", "decide_shift",
    "my_shifts",
}


def linked_employee_id():
    employee_id = getattr(current_user, "employee_id", None)
    if employee_id is None:
        return None
    active = get_db().execute(
        "SELECT 1 FROM employees WHERE id = ? AND active = 1", (employee_id,)
    ).fetchone()
    return employee_id if active is not None else None


def assigned_shifts():
    rows = get_db().execute(
        """SELECT s.id, s.shift_date, s.start_time, s.end_time,
                  s.required_role, s.required_department, s.status
           FROM shifts s JOIN shift_assignments a ON a.shift_id = s.id
           WHERE a.employee_id = ? AND s.status = 'approved'
             AND a.status = 'approved'
           ORDER BY s.shift_date, s.start_time, s.id""",
        (linked_employee_id(),),
    ).fetchall()
    return [dict(row) for row in rows]


def authorize_api_request():
    if request.endpoint == "api.health":
        return None
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    endpoint = request.endpoint.rsplit(".", 1)[-1]
    role = current_user.role
    if role == "admin" and endpoint in ADMIN_ONLY | MANAGER_ACCESS:
        return None
    if role == "manager" and endpoint in MANAGER_ACCESS:
        return None
    if role == "viewer":
        employee_id = linked_employee_id()
        if employee_id is None:
            return jsonify({"error": "An active employee link is required"}), 403
        if endpoint == "my_shifts":
            return None
        if endpoint in VIEWER_OWN and request.view_args.get("employee_id") == employee_id:
            return None
        if endpoint in AVAILABILITY_OWN:
            owned = get_db().execute(
                "SELECT 1 FROM availability WHERE id = ? AND employee_id = ?",
                (request.view_args.get("availability_id"), employee_id),
            ).fetchone()
            if owned is not None:
                return None
    return jsonify({"error": "Permission denied"}), 403
