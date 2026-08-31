from shiftguard.db import seed_demo_data


def _create_employee(client, name):
    response = client.post(
        "/api/employees",
        json={
            "name": name,
            "role": "Nurse",
            "max_weekly_hours": 40,
            "hourly_rate": 30,
        },
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _add_tuesday_availability(client, employee_id):
    response = client.post(
        f"/api/employees/{employee_id}/availability",
        json={"day_of_week": 1, "start_time": "08:00", "end_time": "18:00"},
    )
    assert response.status_code == 201
    return response.get_json()["id"]


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
        json={"start_time": "07:30", "end_time": "17:30"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["start_time"] == "07:30"
    assert updated.get_json()["day_of_week"] == 1

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

