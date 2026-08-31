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

