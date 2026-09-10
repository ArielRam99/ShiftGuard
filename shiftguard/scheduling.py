import json
from datetime import datetime, timedelta

from .ai import StaffingPredictor


def _week_bounds(shift_date):
    start = shift_date - timedelta(days=shift_date.weekday())
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def _approved_weekly_hours(database, employee_ids, shift_date):
    if not employee_ids:
        return {}
    placeholders = ",".join("?" for _ in employee_ids)
    week_start, week_end = _week_bounds(shift_date)
    rows = database.execute(
        f"""
        SELECT sa.employee_id, COALESCE(SUM(s.duration_hours), 0) AS hours
        FROM shift_assignments AS sa
        JOIN shifts AS s ON s.id = sa.shift_id
        WHERE sa.status = 'approved'
          AND s.shift_date BETWEEN ? AND ?
          AND sa.employee_id IN ({placeholders})
        GROUP BY sa.employee_id
        """,
        [week_start, week_end, *employee_ids],
    ).fetchall()
    return {row["employee_id"]: float(row["hours"]) for row in rows}


def _approved_shift_history(database, employee_ids, shift_date):
    if not employee_ids:
        return {}
    placeholders = ",".join("?" for _ in employee_ids)
    history_start = (shift_date - timedelta(days=35)).isoformat()
    history_end = (shift_date + timedelta(days=35)).isoformat()
    rows = database.execute(
        f"""
        SELECT sa.employee_id, s.shift_date, s.start_time, s.end_time
        FROM shift_assignments AS sa
        JOIN shifts AS s ON s.id = sa.shift_id
        WHERE sa.status = 'approved'
          AND s.shift_date BETWEEN ? AND ?
          AND sa.employee_id IN ({placeholders})
        ORDER BY s.shift_date, s.start_time
        """,
        [history_start, history_end, *employee_ids],
    ).fetchall()
    history = {employee_id: [] for employee_id in employee_ids}
    for row in rows:
        history[row["employee_id"]].append(row)
    return history


def _shift_datetimes(shift_date, start_time, end_time):
    return (
        datetime.fromisoformat(f"{shift_date.isoformat()}T{start_time}"),
        datetime.fromisoformat(f"{shift_date.isoformat()}T{end_time}"),
    )


def _has_rest_violation(history, shift_date, start_time, end_time, minimum_hours):
    new_start, new_end = _shift_datetimes(shift_date, start_time, end_time)
    required_rest = timedelta(hours=float(minimum_hours))
    for existing in history:
        existing_date = datetime.fromisoformat(existing["shift_date"]).date()
        old_start, old_end = _shift_datetimes(
            existing_date, existing["start_time"], existing["end_time"]
        )
        if new_start < old_end and new_end > old_start:
            return True
        if old_end <= new_start and new_start - old_end < required_rest:
            return True
        if new_end <= old_start and old_start - new_end < required_rest:
            return True
    return False


def _would_exceed_consecutive_days(history, shift_date, maximum_days):
    worked_dates = {
        datetime.fromisoformat(row["shift_date"]).date() for row in history
    }
    worked_dates.add(shift_date)
    run = 1
    cursor = shift_date - timedelta(days=1)
    while cursor in worked_dates:
        run += 1
        cursor -= timedelta(days=1)
    cursor = shift_date + timedelta(days=1)
    while cursor in worked_dates:
        run += 1
        cursor += timedelta(days=1)
    return run > int(maximum_days)


def _time_off_map(database, employee_ids, shift_date):
    if not employee_ids:
        return {}
    placeholders = ",".join("?" for _ in employee_ids)
    rows = database.execute(
        f"""
        SELECT employee_id, status
        FROM time_off_requests
        WHERE employee_id IN ({placeholders})
          AND status IN ('pending', 'approved')
          AND start_date <= ?
          AND end_date >= ?
        """,
        [*employee_ids, shift_date.isoformat(), shift_date.isoformat()],
    ).fetchall()
    result = {}
    for row in rows:
        statuses = result.setdefault(row["employee_id"], set())
        statuses.add(row["status"])
    return result


def _constraint_warnings(summary):
    labels = {
        "department_mismatch": "department mismatch",
        "unavailable": "not available for the full shift",
        "pending_time_off": "pending time-off request",
        "approved_time_off": "approved time off",
        "insufficient_rest": "minimum-rest violation",
        "consecutive_days": "consecutive-day limit",
        "overtime_not_allowed": "overtime not enabled",
        "overtime_limit": "employee overtime ceiling",
    }
    return [
        f"{count} candidate(s) excluded: {labels[key]}."
        for key, count in summary.get("excluded", {}).items()
        if count and key in labels
    ]


def generate_shift_recommendation(
    database,
    *,
    shift_date,
    start_time,
    end_time,
    duration_hours,
    required_role,
    workload_score,
    required_staff_override=None,
    allow_overtime=False,
    model_strategy="random_forest",
    required_department=None,
):
    history = database.execute(
        """
        SELECT day_of_week, workload_score, shift_length_hours, required_staff
        FROM historical_staffing
        """
    ).fetchall()

    if required_staff_override is None:
        prediction = StaffingPredictor().predict(
            history,
            shift_date.weekday(),
            workload_score,
            duration_hours,
            strategy=model_strategy,
        )
        required_staff = prediction.required_staff
        model_source = prediction.source
        training_records = prediction.training_records
        staffing_range_min = prediction.range_min
        staffing_range_max = prediction.range_max
        confidence_level = prediction.confidence_level
        model_metrics = prediction.metrics
    else:
        required_staff = required_staff_override
        model_source = "manager_override"
        training_records = len(history)
        staffing_range_min = required_staff
        staffing_range_max = required_staff
        confidence_level = None
        model_metrics = None

    cursor = database.execute(
        """
        INSERT INTO shifts (
            shift_date, start_time, end_time, duration_hours,
            required_role, required_department, workload_score,
            required_staff, model_source, staffing_range_min,
            staffing_range_max, confidence_level, model_mae
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shift_date.isoformat(),
            start_time,
            end_time,
            duration_hours,
            required_role,
            required_department,
            workload_score,
            required_staff,
            model_source,
            staffing_range_min,
            staffing_range_max,
            confidence_level,
            model_metrics["mae"] if model_metrics else None,
        ),
    )
    shift_id = cursor.lastrowid

    candidates = database.execute(
        """
        SELECT id, name, role, max_weekly_hours, hourly_rate, department,
               max_overtime_hours, minimum_rest_hours, max_consecutive_days
        FROM employees
        WHERE active = 1 AND LOWER(role) = LOWER(?)
        ORDER BY id
        """,
        (required_role,),
    ).fetchall()
    employee_ids = [row["id"] for row in candidates]
    weekly_hours = _approved_weekly_hours(database, employee_ids, shift_date)
    approved_history = _approved_shift_history(database, employee_ids, shift_date)
    time_off = _time_off_map(database, employee_ids, shift_date)

    excluded = {
        "department_mismatch": 0,
        "unavailable": 0,
        "pending_time_off": 0,
        "approved_time_off": 0,
        "insufficient_rest": 0,
        "consecutive_days": 0,
        "overtime_not_allowed": 0,
        "overtime_limit": 0,
    }
    ranked_candidates = []
    for employee in candidates:
        blockers = []
        if required_department and (
            employee["department"].casefold() != required_department.casefold()
        ):
            blockers.append("department_mismatch")

        availability = database.execute(
            """
            SELECT preference
            FROM availability
            WHERE employee_id = ? AND day_of_week = ?
              AND start_time <= ? AND end_time >= ?
            ORDER BY CASE preference WHEN 'preferred' THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (employee["id"], shift_date.weekday(), start_time, end_time),
        ).fetchone()
        if availability is None:
            blockers.append("unavailable")

        statuses = time_off.get(employee["id"], set())
        if "approved" in statuses:
            blockers.append("approved_time_off")
        elif "pending" in statuses:
            blockers.append("pending_time_off")

        employee_history = approved_history.get(employee["id"], [])
        if _has_rest_violation(
            employee_history,
            shift_date,
            start_time,
            end_time,
            employee["minimum_rest_hours"],
        ):
            blockers.append("insufficient_rest")
        if _would_exceed_consecutive_days(
            employee_history, shift_date, employee["max_consecutive_days"]
        ):
            blockers.append("consecutive_days")

        current_hours = weekly_hours.get(employee["id"], 0.0)
        projected_hours = current_hours + duration_hours
        overtime_hours = max(0.0, projected_hours - employee["max_weekly_hours"])
        if overtime_hours > 0 and not allow_overtime:
            blockers.append("overtime_not_allowed")
        if overtime_hours > employee["max_overtime_hours"]:
            blockers.append("overtime_limit")

        if blockers:
            for blocker in set(blockers):
                excluded[blocker] += 1
            continue

        recent_start = shift_date - timedelta(days=28)
        recent_assignments = sum(
            recent_start <= datetime.fromisoformat(row["shift_date"]).date() < shift_date
            for row in employee_history
        )
        utilization = current_hours / employee["max_weekly_hours"]
        preferred_bonus = 6 if availability["preference"] == "preferred" else 0
        score = (
            100
            - (utilization * 45)
            - (overtime_hours * 12)
            - (recent_assignments * 3)
            + preferred_bonus
        )
        reason_parts = [
            f"{availability['preference'].capitalize()} for the full shift",
            (
                f"projected weekly hours {projected_hours:.1f}/"
                f"{employee['max_weekly_hours']:.1f}"
            ),
            f"{recent_assignments} approved shift(s) in the prior 28 days",
        ]
        if overtime_hours:
            reason_parts.append(f"{overtime_hours:.1f} overtime hours")
        else:
            reason_parts.append("no overtime projected")

        ranked_candidates.append(
            {
                "employee": employee,
                "score": round(score, 2),
                "projected_hours": round(projected_hours, 2),
                "overtime_hours": round(overtime_hours, 2),
                "reason": "; ".join(reason_parts),
            }
        )

    ranked_candidates.sort(
        key=lambda item: (-item["score"], item["employee"]["id"])
    )
    selected = ranked_candidates[:required_staff]
    for item in selected:
        database.execute(
            """
            INSERT INTO shift_assignments (
                shift_id, employee_id, recommendation_score,
                projected_weekly_hours, projected_overtime_hours, reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                shift_id,
                item["employee"]["id"],
                item["score"],
                item["projected_hours"],
                item["overtime_hours"],
                item["reason"],
            ),
        )

    constraint_summary = {
        "considered_candidates": len(candidates),
        "eligible_candidates": len(ranked_candidates),
        "selected_candidates": len(selected),
        "excluded": excluded,
        "fairness_policy": (
            "Prefer lower weekly utilization and fewer approved shifts in the "
            "prior 28 days; hourly rate is not used for ranking."
        ),
    }
    database.execute(
        "UPDATE shifts SET constraint_summary = ? WHERE id = ?",
        (json.dumps(constraint_summary, sort_keys=True), shift_id),
    )
    database.commit()

    result = get_shift(database, shift_id)
    result["training_records"] = training_records
    result["coverage_gap"] = max(0, required_staff - len(selected))
    result["requires_manager_approval"] = True
    if model_metrics:
        result["model_metrics"] = model_metrics
    return result


def get_shift(database, shift_id):
    shift = database.execute(
        "SELECT * FROM shifts WHERE id = ?", (shift_id,)
    ).fetchone()
    if shift is None:
        return None

    assignments = database.execute(
        """
        SELECT
            sa.id,
            sa.employee_id,
            e.name AS employee_name,
            e.role,
            e.department,
            sa.recommendation_score,
            sa.projected_weekly_hours,
            sa.projected_overtime_hours,
            sa.reason,
            sa.status
        FROM shift_assignments AS sa
        JOIN employees AS e ON e.id = sa.employee_id
        WHERE sa.shift_id = ?
        ORDER BY sa.recommendation_score DESC, sa.id
        """,
        (shift_id,),
    ).fetchall()
    try:
        constraint_summary = json.loads(shift["constraint_summary"] or "{}")
    except (TypeError, json.JSONDecodeError):
        constraint_summary = {}

    return {
        "id": shift["id"],
        "shift_date": shift["shift_date"],
        "start_time": shift["start_time"],
        "end_time": shift["end_time"],
        "duration_hours": shift["duration_hours"],
        "required_role": shift["required_role"],
        "required_department": shift["required_department"],
        "workload_score": shift["workload_score"],
        "required_staff": shift["required_staff"],
        "model_source": shift["model_source"],
        "staffing_range": {
            "minimum": shift["staffing_range_min"],
            "maximum": shift["staffing_range_max"],
            "confidence_level": shift["confidence_level"],
        },
        "model_mae": shift["model_mae"],
        "constraint_summary": constraint_summary,
        "constraint_warnings": _constraint_warnings(constraint_summary),
        "status": shift["status"],
        "decided_by": shift["decided_by"],
        "manager_note": shift["manager_note"],
        "created_at": shift["created_at"],
        "decided_at": shift["decided_at"],
        "assignments": [dict(row) for row in assignments],
        "requires_manager_approval": shift["status"] == "draft",
    }
