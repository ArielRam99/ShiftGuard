def test_dashboard_and_assets_are_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert b"ShiftGuard" in response.data
    assert client.get("/static/dashboard.js").status_code == 200


def test_sample_csv_is_downloadable(client):
    response = client.get("/sample-data.csv")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data.startswith(
        b"date,day_of_week,workload_hours,actual_headcount"
    )