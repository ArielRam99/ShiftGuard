from datetime import timedelta

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
        )
        required_staff = prediction.required_staff
        model_source = prediction.source
        training_records = prediction.training_records
    else:
        required_staff = required_staff_override
        model_source = "manager_override"
        training_records = len(history)

    cursor = database.execute(
        """
        INSERT INTO shifts (
            shift_date, start_time, end_time, duration_hours,
            required_role, workload_score, required_staff, model_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shift_date.isoformat(),
            start_time,
            end_time,
            duration_hours,
            required_role,
            workload_score,
            required_staff,
            model_source,
        ),
    )
    shift_id = cursor.lastrowid

    candidates = database.execute(
        """
        SELECT DISTINCT e.id, e.name, e.role, e.max_weekly_hours, e.hourly_rate
        FROM employees AS e
        JOIN availability AS a ON a.employee_id = e.id
        WHERE e.active = 1
          AND LOWER(e.role) = LOWER(?)
          AND a.day_of_week = ?
          AND a.start_time <= ?
          AND a.end_time >= ?
        """,
        (required_role, shift_date.weekday(), start_time, end_time),
    ).fetchall()

    weekly_hours = _approved_weekly_hours(
        database, [row["id"] for row in candidates], shift_date
    )
    ranked_candidates = []
    for employee in candidates:
        current_hours = weekly_hours.get(employee["id"], 0.0)
        projected_hours = current_hours + duration_hours
        overtime_hours = max(0.0, projected_hours - employee["max_weekly_hours"])
        if overtime_hours > 0 and not allow_overtime:
            continue

        utilization = current_hours / employee["max_weekly_hours"]
        score = 100 - (utilization * 55) - (overtime_hours * 12)
        reason = (
            f"Available for the full shift; projected weekly hours "
            f"{projected_hours:.1f}/{employee['max_weekly_hours']:.1f}"
        )
        if overtime_hours:
            reason += f"; includes {overtime_hours:.1f} overtime hours"
        else:
            reason += "; no overtime projected"

        ranked_candidates.append(
            {
                "employee": employee,
                "score": round(score, 2),
                "projected_hours": round(projected_hours, 2),
                "overtime_hours": round(overtime_hours, 2),
                "reason": reason,
            }
        )

    ranked_candidates.sort(
        key=lambda item: (
            -item["score"],
            item["employee"]["hourly_rate"],
            item["employee"]["id"],
        )
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

    database.commit()
    result = get_shift(database, shift_id)
    result["training_records"] = training_records
    result["coverage_gap"] = max(0, required_staff - len(selected))
    result["requires_manager_approval"] = True
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

    return {
        "id": shift["id"],
        "shift_date": shift["shift_date"],
        "start_time": shift["start_time"],
        "end_time": shift["end_time"],
        "duration_hours": shift["duration_hours"],
        "required_role": shift["required_role"],
        "workload_score": shift["workload_score"],
        "required_staff": shift["required_staff"],
        "model_source": shift["model_source"],
        "status": shift["status"],
        "decided_by": shift["decided_by"],
        "manager_note": shift["manager_note"],
        "created_at": shift["created_at"],
        "decided_at": shift["decided_at"],
        "assignments": [dict(row) for row in assignments],
        "requires_manager_approval": shift["status"] == "draft",
    }

