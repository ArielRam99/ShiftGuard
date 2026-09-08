from io import BytesIO

from openpyxl import load_workbook

from shiftguard.db import seed_demo_data


def _create_employee(client, name, **overrides):
    payload = {
        "name": name,
        "role": "Nurse",
        "max_weekly_hours": 40,
        "hourly_rate": 30,
    }
    payload.update(overrides)
    response = client.post(
        "/api/employees",
        json=payload,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _add_availability(
    client,
    employee_id,
    day_of_week=1,
    start_time="08:00",
    end_time="18:00",
    preference="available",
):
    response = client.post(
        f"/api/employees/{employee_id}/availability",
        json={
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "preference": preference,
        },
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _add_tuesday_availability(client, employee_id):
    return _add_availability(client, employee_id)


def _assign_skill(client, employee_id, skill_name, proficiency=3):
    response = client.post(
        f"/api/employees/{employee_id}/skills",
        json={"skill_name": skill_name, "proficiency": proficiency},
    )
    assert response.status_code == 201
    return response.get_json()


def _recommend(client, shift_date, **overrides):
    payload = {
        "shift_date": shift_date,
        "start_time": "09:00",
        "end_time": "17:00",
        "required_role": "Nurse",
        "workload_score": 50,
        "required_staff": 1,
    }
    payload.update(overrides)
    response = client.post("/api/shifts/recommendations", json=payload)
    assert response.status_code == 201
    return response.get_json()


def _approve(client, shift_id):
    response = client.patch(
        f"/api/shifts/{shift_id}/decision",
        json={"decision": "approved", "manager_name": "Phase B Manager"},
    )
    assert response.status_code == 200
    return response.get_json()


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"service": "ShiftGuard AI", "status": "ok"}


def test_complete_manager_approval_workflow(client):
    employee_ids = [_create_employee(client, "Alex One"), _create_employee(client, "Alex Two")]
    for employee_id in employee_ids:
        _add_tuesday_availability(client, employee_id)

    recommendation = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 60,
            "required_staff": 2,
        },
    )
    assert recommendation.status_code == 201
    proposed = recommendation.get_json()
    assert proposed["status"] == "draft"
    assert proposed["model_source"] == "manager_override"
    assert proposed["coverage_gap"] == 0
    assert proposed["requires_manager_approval"] is True
    assert len(proposed["assignments"]) == 2
    assert all(
        assignment["projected_overtime_hours"] == 0
        for assignment in proposed["assignments"]
    )

    approval = client.patch(
        f"/api/shifts/{proposed['id']}/decision",
        json={
            "decision": "approved",
            "manager_name": "Demo Manager",
            "manager_note": "Availability confirmed.",
        },
    )
    assert approval.status_code == 200
    approved = approval.get_json()
    assert approved["status"] == "approved"
    assert approved["decided_by"] == "Demo Manager"
    assert approved["requires_manager_approval"] is False
    assert all(item["status"] == "approved" for item in approved["assignments"])


def test_seeded_history_uses_machine_learning_model(app, client):
    with app.app_context():
        seed_demo_data()

    status = client.get("/api/model/status").get_json()
    assert status["training_records"] >= 5
    assert status["strategy"] == "random_forest"

    response = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 80,
        },
    )
    assert response.status_code == 201
    result = response.get_json()
    assert result["model_source"] == "random_forest"
    assert result["required_staff"] >= 1
    assert result["training_records"] >= 5
    assert result["requires_manager_approval"] is True


def test_recommendation_reports_coverage_gap(client):
    response = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 70,
            "required_staff": 2,
        },
    )
    assert response.status_code == 201
    result = response.get_json()
    assert result["coverage_gap"] == 2
    assert result["assignments"] == []


def test_rejects_invalid_shift_time(client):
    response = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "18:00",
            "end_time": "09:00",
            "required_role": "Nurse",
            "workload_score": 50,
        },
    )
    assert response.status_code == 400
    assert "Overnight shifts" in response.get_json()["error"]


def test_list_update_and_delete_employee_availability(client):
    employee_id = _create_employee(client, "Availability User")
    first_id = _add_tuesday_availability(client, employee_id)
    second = client.post(
        f"/api/employees/{employee_id}/availability",
        json={"day_of_week": 3, "start_time": "10:00", "end_time": "16:00"},
    )
    assert second.status_code == 201

    listed = client.get(f"/api/employees/{employee_id}/availability")
    assert listed.status_code == 200
    assert [item["day_of_week"] for item in listed.get_json()["availability"]] == [1, 3]

    updated = client.patch(
        f"/api/availability/{first_id}",
        json={
            "start_time": "07:30",
            "end_time": "17:30",
            "preference": "preferred",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["start_time"] == "07:30"
    assert updated.get_json()["day_of_week"] == 1
    assert updated.get_json()["preference"] == "preferred"

    deleted = client.delete(f"/api/availability/{first_id}")
    assert deleted.status_code == 204
    assert deleted.data == b""

    after_delete = client.get(f"/api/employees/{employee_id}/availability")
    remaining = after_delete.get_json()["availability"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == second.get_json()["id"]

    missing = client.patch(
        f"/api/availability/{first_id}", json={"day_of_week": 2}
    )
    assert missing.status_code == 404


def test_get_employee_by_id(client):
    employee_id = _create_employee(client, "Lookup Employee")

    response = client.get(f"/api/employees/{employee_id}")
    assert response.status_code == 200

    employee = response.get_json()
    assert employee["id"] == employee_id
    assert employee["name"] == "Lookup Employee"
    assert employee["role"] == "Nurse"
    assert employee["max_weekly_hours"] == 40
    assert employee["hourly_rate"] == 30

    missing = client.get("/api/employees/99999")
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "Employee not found"


def test_filter_employees(client):
    nurse_id = _create_employee(
        client,
        "Clinical Nurse",
        department="Clinical",
    )
    _create_employee(
        client,
        "Emergency Nurse",
        department="Emergency",
    )
    inactive_id = _create_employee(
        client,
        "Inactive Nurse",
        department="Clinical",
    )

    deactivate = client.patch(
        f"/api/employees/{inactive_id}",
        json={"active": False},
    )
    assert deactivate.status_code == 200

    by_role = client.get("/api/employees?role=Nurse")
    assert by_role.status_code == 200
    assert all(
        employee["role"] == "Nurse"
        for employee in by_role.get_json()["employees"]
    )

    by_department = client.get("/api/employees?department=Clinical")
    assert by_department.status_code == 200
    assert all(
        employee["department"] == "Clinical"
        for employee in by_department.get_json()["employees"]
    )

    combined = client.get(
        "/api/employees?role=Nurse&department=Clinical&active=true"
    )
    assert combined.status_code == 200
    employee_ids = [
        employee["id"]
        for employee in combined.get_json()["employees"]
    ]
    assert nurse_id in employee_ids
    assert inactive_id not in employee_ids

    invalid = client.get("/api/employees?active=maybe")
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "'active' must be true or false"


def test_update_and_deactivate_employee(client):
    employee_id = _create_employee(client, "Employee Before")
    _add_tuesday_availability(client, employee_id)

    response = client.patch(
        f"/api/employees/{employee_id}",
        json={
            "name": "Employee After",
            "role": "Supervisor",
            "max_weekly_hours": 35,
            "hourly_rate": 42.5,
            "active": False,
        },
    )
    assert response.status_code == 200
    employee = response.get_json()
    assert employee["name"] == "Employee After"
    assert employee["role"] == "Supervisor"
    assert employee["max_weekly_hours"] == 35
    assert employee["hourly_rate"] == 42.5
    assert employee["active"] == 0

    recommendation = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Supervisor",
            "workload_score": 50,
            "required_staff": 1,
        },
    )
    assert recommendation.status_code == 201
    assert recommendation.get_json()["assignments"] == []
    assert recommendation.get_json()["coverage_gap"] == 1

    invalid = client.patch(
        f"/api/employees/{employee_id}", json={"active": "no"}
    )
    assert invalid.status_code == 400


def test_employee_constraints_and_preferred_skill_routing(client):
    preferred_id = _create_employee(
        client,
        "Preferred Specialist",
        department="Emergency",
        max_overtime_hours=4,
        minimum_rest_hours=10,
        max_consecutive_days=5,
    )
    missing_skill_id = _create_employee(
        client, "Missing Skill", department="Emergency"
    )
    other_department_id = _create_employee(
        client, "Other Department", department="Surgery"
    )
    _add_availability(client, preferred_id, preference="preferred")
    _add_availability(client, missing_skill_id)
    _add_availability(client, other_department_id)
    skill = _assign_skill(client, preferred_id, "Triage", proficiency=5)
    _assign_skill(client, other_department_id, "Triage")

    employee = client.get("/api/employees").get_json()["employees"][0]
    employee_by_id = {
        item["id"]: item
        for item in client.get("/api/employees").get_json()["employees"]
    }
    assert employee  # confirms the existing list envelope is unchanged
    assert employee_by_id[preferred_id]["department"] == "Emergency"
    assert employee_by_id[preferred_id]["max_overtime_hours"] == 4
    assert employee_by_id[preferred_id]["minimum_rest_hours"] == 10
    assert employee_by_id[preferred_id]["max_consecutive_days"] == 5

    assigned = client.get(f"/api/employees/{preferred_id}/skills")
    assert assigned.status_code == 200
    assert assigned.get_json()["skills"][0]["name"] == "Triage"
    catalog = client.get("/api/skills")
    assert [item["name"] for item in catalog.get_json()["skills"]] == ["Triage"]

    result = _recommend(
        client,
        "2026-09-01",
        required_staff=2,
        required_department="Emergency",
        required_skills=["Triage"],
    )
    assert result["required_department"] == "Emergency"
    assert result["required_skills"] == ["Triage"]
    assert [item["employee_id"] for item in result["assignments"]] == [preferred_id]
    assert "Preferred for the full shift" in result["assignments"][0]["reason"]
    assert result["coverage_gap"] == 1
    excluded = result["constraint_summary"]["excluded"]
    assert excluded["missing_skills"] == 1
    assert excluded["department_mismatch"] == 1
    assert "hourly rate is not used" in result["constraint_summary"]["fairness_policy"]
    fetched = client.get(f"/api/shifts/{result['id']}").get_json()
    assert fetched["constraint_summary"] == result["constraint_summary"]
    assert fetched["constraint_warnings"] == result["constraint_warnings"]
    department_filter = client.get(
        "/api/shifts?required_department=emergency"
    ).get_json()["shifts"]
    assert [shift["id"] for shift in department_filter] == [result["id"]]

    removed = client.delete(
        f"/api/employees/{preferred_id}/skills/{skill['id']}"
    )
    assert removed.status_code == 204
    assert client.get(
        f"/api/employees/{preferred_id}/skills"
    ).get_json()["skills"] == []


def test_time_off_workflow_blocks_pending_and_approved_requests(client):
    employee_id = _create_employee(client, "Time Off Employee")
    _add_tuesday_availability(client, employee_id)
    created = client.post(
        f"/api/employees/{employee_id}/time-off",
        json={
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
            "reason": "Family commitment",
        },
    )
    assert created.status_code == 201
    request_item = created.get_json()
    assert request_item["status"] == "pending"

    employee_list = client.get(
        f"/api/employees/{employee_id}/time-off?status=pending"
    )
    assert employee_list.status_code == 200
    assert len(employee_list.get_json()["time_off_requests"]) == 1
    manager_list = client.get("/api/time-off?status=pending")
    assert manager_list.get_json()["time_off_requests"][0]["employee_name"] == (
        "Time Off Employee"
    )

    pending_result = _recommend(client, "2026-09-01")
    assert pending_result["assignments"] == []
    assert pending_result["constraint_summary"]["excluded"]["pending_time_off"] == 1

    approved = client.patch(
        f"/api/time-off/{request_item['id']}/decision",
        json={
            "decision": "approved",
            "manager_name": "Phase B Manager",
            "manager_note": "Coverage confirmed",
        },
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "approved"
    assert approved.get_json()["decided_by"] == "Phase B Manager"

    approved_result = _recommend(client, "2026-09-01")
    assert approved_result["assignments"] == []
    assert (
        approved_result["constraint_summary"]["excluded"]["approved_time_off"] == 1
    )
    repeated = client.patch(
        f"/api/time-off/{request_item['id']}/decision",
        json={"decision": "rejected", "manager_name": "Phase B Manager"},
    )
    assert repeated.status_code == 409

    available_id = _create_employee(client, "Rejected Time Off")
    _add_tuesday_availability(client, available_id)
    second_request = client.post(
        f"/api/employees/{available_id}/time-off",
        json={"start_date": "2026-09-01", "end_date": "2026-09-01"},
    ).get_json()
    rejected = client.patch(
        f"/api/time-off/{second_request['id']}/decision",
        json={"decision": "rejected", "manager_name": "Phase B Manager"},
    )
    assert rejected.status_code == 200
    after_rejection = _recommend(client, "2026-09-01")
    assert [item["employee_id"] for item in after_rejection["assignments"]] == [
        available_id
    ]


def test_minimum_rest_and_consecutive_day_limits(client):
    rest_id = _create_employee(
        client,
        "Rest Guard",
        department="Clinical",
        minimum_rest_hours=11,
        max_consecutive_days=6,
    )
    _add_availability(client, rest_id, day_of_week=0, start_time="06:00", end_time="23:00")
    _add_availability(client, rest_id, day_of_week=1, start_time="05:00", end_time="18:00")
    monday = _recommend(
        client,
        "2026-08-31",
        start_time="14:00",
        end_time="22:00",
    )
    _approve(client, monday["id"])
    too_soon = _recommend(
        client,
        "2026-09-01",
        start_time="06:00",
        end_time="14:00",
    )
    assert too_soon["assignments"] == []
    assert too_soon["constraint_summary"]["excluded"]["insufficient_rest"] == 1

    consecutive_id = _create_employee(
        client,
        "Consecutive Guard",
        minimum_rest_hours=8,
        max_consecutive_days=2,
    )
    for day in (6, 0, 1):
        _add_availability(client, consecutive_id, day_of_week=day)
    sunday = _recommend(client, "2026-08-30")
    _approve(client, sunday["id"])
    monday = _recommend(client, "2026-08-31")
    _approve(client, monday["id"])
    tuesday = _recommend(client, "2026-09-01")
    assignment_ids = [item["employee_id"] for item in tuesday["assignments"]]
    assert consecutive_id not in assignment_ids
    assert tuesday["constraint_summary"]["excluded"]["consecutive_days"] >= 1


def test_overtime_ceiling_and_fairness_ranking(client):
    overtime_id = _create_employee(
        client,
        "Overtime Guard",
        max_weekly_hours=8,
        max_overtime_hours=2,
        minimum_rest_hours=8,
    )
    _add_availability(client, overtime_id, day_of_week=0)
    _add_availability(client, overtime_id, day_of_week=1)
    monday = _recommend(client, "2026-08-31")
    _approve(client, monday["id"])
    overtime = _recommend(client, "2026-09-01", allow_overtime=True)
    assert overtime_id not in [
        item["employee_id"] for item in overtime["assignments"]
    ]
    assert overtime["constraint_summary"]["excluded"]["overtime_limit"] == 1

    experienced_id = _create_employee(
        client, "Recently Scheduled", minimum_rest_hours=8
    )
    fresh_id = _create_employee(client, "Fresh Candidate", minimum_rest_hours=8)
    for employee_id in (experienced_id, fresh_id):
        _add_availability(client, employee_id, day_of_week=0)
        _add_availability(client, employee_id, day_of_week=1)
    prior = _recommend(client, "2026-08-31", required_staff=1)
    assert prior["assignments"][0]["employee_id"] == experienced_id
    _approve(client, prior["id"])
    fair = _recommend(client, "2026-09-01", required_staff=1)
    assert fair["assignments"][0]["employee_id"] == fresh_id
    assert "0 approved shift(s)" in fair["assignments"][0]["reason"]


def test_list_and_filter_schedules(client):
    employee_id = _create_employee(client, "Schedule Filter User")
    _add_tuesday_availability(client, employee_id)

    approved_response = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 50,
            "required_staff": 1,
        },
    )
    approved_id = approved_response.get_json()["id"]
    client.patch(
        f"/api/shifts/{approved_id}/decision",
        json={"decision": "approved", "manager_name": "Filter Manager"},
    )

    client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-08",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 50,
            "required_staff": 1,
        },
    )
    client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-02",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Cashier",
            "workload_score": 50,
            "required_staff": 1,
        },
    )

    all_shifts = client.get("/api/shifts")
    assert all_shifts.status_code == 200
    assert len(all_shifts.get_json()["shifts"]) == 3

    filtered = client.get(
        "/api/shifts",
        query_string={
            "date_from": "2026-09-01",
            "date_to": "2026-09-07",
            "required_role": "nurse",
            "status": "approved",
            "employee_id": employee_id,
        },
    )
    assert filtered.status_code == 200
    shifts = filtered.get_json()["shifts"]
    assert [shift["id"] for shift in shifts] == [approved_id]

    invalid_range = client.get(
        "/api/shifts?date_from=2026-09-10&date_to=2026-09-01"
    )
    assert invalid_range.status_code == 400

    invalid_status = client.get("/api/shifts?status=published")
    assert invalid_status.status_code == 400


def test_model_comparison_selection_and_confidence_range(app, client):
    with app.app_context():
        seed_demo_data()

    comparison_response = client.get("/api/model/comparison")
    assert comparison_response.status_code == 200
    comparison = comparison_response.get_json()
    assert comparison["training_records"] == 35
    assert comparison["best_model"] in {
        "random_forest",
        "gradient_boosting",
        "linear_regression",
    }
    assert {result["strategy"] for result in comparison["models"]} == {
        "random_forest",
        "gradient_boosting",
        "linear_regression",
    }
    assert all(result["mae"] >= 0 for result in comparison["models"])

    for strategy in (
        "random_forest",
        "gradient_boosting",
        "linear_regression",
        "auto",
    ):
        response = client.post(
            "/api/shifts/recommendations",
            json={
                "shift_date": "2026-09-01",
                "start_time": "09:00",
                "end_time": "17:00",
                "required_role": "Nurse",
                "workload_score": 80,
                "model_strategy": strategy,
            },
        )
        assert response.status_code == 201
        result = response.get_json()
        assert result["model_source"] in {
            "random_forest",
            "gradient_boosting",
            "linear_regression",
        }
        assert result["staffing_range"]["minimum"] <= result["required_staff"]
        assert result["staffing_range"]["maximum"] >= result["required_staff"]
        assert result["staffing_range"]["confidence_level"] == 0.95
        assert result["model_metrics"]["mae"] >= 0

    invalid = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 80,
            "model_strategy": "neural_network",
        },
    )
    assert invalid.status_code == 400


def test_schedule_and_analytics_reports(app, client):
    with app.app_context():
        seed_demo_data()

    recommendation = client.post(
        "/api/shifts/recommendations",
        json={
            "shift_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "required_role": "Nurse",
            "workload_score": 80,
        },
    )
    assert recommendation.status_code == 201

    schedule_pdf = client.get("/api/reports/schedules.pdf")
    assert schedule_pdf.status_code == 200
    assert schedule_pdf.data.startswith(b"%PDF")
    assert "shiftguard-schedules.pdf" in schedule_pdf.headers["Content-Disposition"]

    schedule_xlsx = client.get("/api/reports/schedules.xlsx")
    assert schedule_xlsx.status_code == 200
    assert schedule_xlsx.data.startswith(b"PK")
    assert "shiftguard-schedules.xlsx" in schedule_xlsx.headers["Content-Disposition"]
    workbook = load_workbook(BytesIO(schedule_xlsx.data), read_only=True)
    schedule_headers = [cell.value for cell in next(workbook["Schedules"].rows)]
    assignment_headers = [cell.value for cell in next(workbook["Assignments"].rows)]
    assert "Department" in schedule_headers
    assert "Required Skills" in schedule_headers
    assert "Department" in assignment_headers

    analytics_pdf = client.get("/api/reports/analytics.pdf")
    assert analytics_pdf.status_code == 200
    assert analytics_pdf.data.startswith(b"%PDF")

    analytics_xlsx = client.get("/api/reports/analytics.xlsx")
    assert analytics_xlsx.status_code == 200
    assert analytics_xlsx.data.startswith(b"PK")

    invalid_format = client.get("/api/reports/schedules.csv")
    assert invalid_format.status_code == 404
