# ShiftGuard AI

ShiftGuard AI is a workforce-scheduling MVP that recommends staffing levels and
employees while helping managers reduce understaffing, overtime, and burnout.
Its recommendations are advisory: a manager must explicitly approve or reject
every generated schedule.

## What this MVP includes

- Flask JSON API for employees, availability, and shift recommendations
- SQLite persistence with parameterized queries and foreign-key enforcement
- Scikit-learn random-forest demand prediction when enough history exists
- Documented rules-based fallback for a new installation
- Employee ranking based on availability and projected weekly hours
- Overtime avoidance by default, with an explicit opt-in override
- Manager approval/rejection workflow and decision audit fields
- Pytest coverage and a GitHub Actions test workflow

## Architecture

| Component | Responsibility |
| --- | --- |
| `shiftguard/api.py` | Validates requests and exposes the integration API |
| `shiftguard/db.py` | Manages SQLite, schema initialization, and demo data |
| `shiftguard/ai.py` | Predicts required staffing from historical demand |
| `shiftguard/scheduling.py` | Filters, ranks, and stores employee recommendations |
| `shiftguard/schema.sql` | Defines employees, availability, history, shifts, and assignments |

The request flow is: application/UI → Flask API → prediction and scheduling
services → SQLite → manager decision endpoint.

## Install and run

Python 3.10 or newer is recommended.

### Windows PowerShell

```powershell
git clone https://github.com/peputski/ShiftGuard.git
cd ShiftGuard
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements-dev.txt
py -m flask --app app seed-demo
py -m flask --app app run --debug
```

If PowerShell blocks virtual-environment activation, run this once in the
current terminal and then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### WSL, Linux, or macOS

```bash
git clone https://github.com/peputski/ShiftGuard.git
cd ShiftGuard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m flask --app app seed-demo
python -m flask --app app run --debug
```

The API will be available at `http://127.0.0.1:5000`. The database is created
under `instance/shiftguard.sqlite` and is intentionally excluded from Git.

## Try the API

Check the service:

```bash
curl http://127.0.0.1:5000/api/health
```

Generate a draft recommendation from the seeded data:

```bash
curl -X POST http://127.0.0.1:5000/api/shifts/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "shift_date": "2026-09-01",
    "start_time": "09:00",
    "end_time": "17:00",
    "required_role": "Nurse",
    "workload_score": 80
  }'
```

Approve the draft after reviewing it, replacing `1` with the returned shift ID:

```bash
curl -X PATCH http://127.0.0.1:5000/api/shifts/1/decision \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approved",
    "manager_name": "Manager Name",
    "manager_note": "Availability confirmed with the team."
  }'
```

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Service and database health check |
| `GET` | `/api/model/status` | Model strategy and training-record count |
| `GET` | `/api/employees` | List employees |
| `POST` | `/api/employees` | Create an employee |
| `PATCH` | `/api/employees/{id}` | Update, deactivate, or reactivate an employee |
| `GET` | `/api/employees/{id}/availability` | List weekly availability |
| `POST` | `/api/employees/{id}/availability` | Add weekly availability |
| `PATCH` | `/api/availability/{id}` | Update weekly availability |
| `DELETE` | `/api/availability/{id}` | Delete weekly availability |
| `GET` | `/api/shifts` | List and filter schedules |
| `POST` | `/api/shifts/recommendations` | Generate and save a draft schedule |
| `GET` | `/api/shifts/{id}` | Retrieve a draft or decided schedule |
| `PATCH` | `/api/shifts/{id}/decision` | Manager approval or rejection |

`day_of_week` uses `0` for Monday through `6` for Sunday. Overnight shifts are
outside this first MVP and are rejected explicitly.

Schedule-list filters are `date_from`, `date_to`, `required_role`, `status`, and
`employee_id`. See `docs/openapi.yaml` for the authoritative request and
response contract.

## Run tests

```bash
python -m pytest -q
```

GitHub Actions also runs the same tests for each pull request and each push to
`main`.

## Responsible-use boundaries

- Recommendations never become final schedules automatically.
- The API records who approved or rejected a recommendation.
- Overtime is excluded unless the caller explicitly sets `allow_overtime`.
- The score uses operational data only; it does not use protected personal
  characteristics.
- A production version still needs authentication, authorization, encrypted
  deployment, formal database migrations, monitoring, and bias evaluation.

