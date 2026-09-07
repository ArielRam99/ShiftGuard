# ShiftGuard AI

ShiftGuard AI is a workforce-scheduling MVP that recommends staffing levels and
employees while helping managers reduce understaffing, overtime, and burnout.
Its recommendations are advisory: a manager must explicitly approve or reject
every generated schedule.

## What this MVP includes

- Flask JSON API for employees, preferred availability, skills, time off, and
  shift recommendations
- Responsive Tailwind manager dashboard for staffing predictions, model
  comparison, CSV training-data import, and schedule decisions
- SQLite persistence with parameterized queries and foreign-key enforcement
- Scikit-learn Random Forest, Gradient Boosting, and Linear Regression models
- Reproducible model comparison with automatic lowest-error selection
- Persisted 95% operational staffing ranges for demand-spike planning
- PDF and formatted Excel schedule and analytics exports
- Documented rules-based fallback for a new installation
- Department and skill-aware assignment matching
- Pending and approved time-off protection with a manager decision workflow
- Configurable minimum-rest, consecutive-day, and weekly overtime ceilings
- Workload-balancing ranking based on weekly utilization, recent approved
  shifts, preferences, and skill proficiency—not hourly rate
- Overtime avoidance by default; opt-in overtime remains capped per employee
- Manager approval/rejection workflow and decision audit fields
- Pytest coverage and a GitHub Actions test workflow

## Architecture

| Component | Responsibility |
| --- | --- |
| `shiftguard/api.py` | Validates requests and exposes the integration API |
| `shiftguard/db.py` | Manages SQLite, schema initialization, and demo data |
| `shiftguard/ai.py` | Predicts required staffing from historical demand |
| `shiftguard/reports.py` | Generates downloadable PDF and Excel reports |
| `shiftguard/scheduling.py` | Filters, ranks, and stores employee recommendations |
| `shiftguard/schema.sql` | Defines employees, preferences, skills, time off, shifts, and assignments |

The request flow is: application/UI → Flask API → prediction and scheduling
services → SQLite → manager decision endpoint.

## Run locally

Prerequisites are Git, Python 3.10 or newer, and internet access for Python
packages and the dashboard's Tailwind CSS, Lucide icons, and display fonts.

### Windows PowerShell

1. Create a `ShiftGuard` folder and clone the repository into it:

  ```powershell
  New-Item -ItemType Directory ShiftGuard
  cd ShiftGuard
  git clone https://github.com/ArielRam99/ShiftGuard.git .
  ```

2. Create and activate a virtual environment:

  ```powershell
  py -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

  If PowerShell blocks activation, allow scripts for this terminal and retry:

  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
  ```

3. Install all application and unit-test dependencies from `requirements.txt`:

  ```powershell
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  ```

4. Create the database and load demonstration data:

  ```powershell
  python -m flask --app app seed-demo
  ```

  The expected output is `Loaded ShiftGuard demo data.` Running this command
  again is safe because existing seed records are ignored.

5. Start the application:

  ```powershell
  python -m flask --app app run --debug
  ```

  Open `http://127.0.0.1:5000`. From another PowerShell terminal, verify the
  API with:

  ```powershell
  Invoke-RestMethod http://127.0.0.1:5000/api/health
  ```

  The response should contain `status` set to `ok`. Stop Flask with `Ctrl+C`.

6. Run the unit tests from the repository root with the environment active:

  ```powershell
  python -m pytest -v
  ```

### WSL, Linux, or macOS

1. Clone into a new `ShiftGuard` directory:

  ```bash
  mkdir ShiftGuard
  cd ShiftGuard
  git clone https://github.com/ArielRam99/ShiftGuard.git .
  ```

2. Create the environment and install `requirements.txt`:

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  ```

3. Seed and run the application:

  ```bash
  python -m flask --app app seed-demo
  python -m flask --app app run --debug
  ```

  Open `http://127.0.0.1:5000`, or verify the API from another terminal with
  `curl http://127.0.0.1:5000/api/health`. Stop Flask with `Ctrl+C`.

4. Run the unit tests:

  ```bash
  python -m pytest -v
  ```

The database is created at `instance/shiftguard.sqlite`. The Flask server and
tests run as separate commands because the server occupies its terminal until
it is stopped.

## Use the dashboard

Open `http://127.0.0.1:5000` while the Flask development server is running.
The **Schedule** view predicts staffing and ranks eligible employees. Choose
Auto, Random Forest, Gradient Boosting, or Linear Regression before generating
a draft, then approve or reject it with a manager name.

The **Training data** view accepts UTF-8 CSV files with these exact columns:

```text
date,day_of_week,workload_hours,actual_headcount
```

`day_of_week` is checked against `date`, `workload_hours` is imported as the
0-100 workload score, and `actual_headcount` is the required staff target.
Imported records use an eight-hour shift length. The full file is validated
before anything is written, and duplicate observations are skipped.

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
    "workload_score": 80,
    "model_strategy": "auto"
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
| `GET` | `/api/model/comparison` | Compare model accuracy and select the best model |
| `POST` | `/api/historical-staffing/import` | Import historical staffing data from CSV |
| `GET` | `/api/employees` | List employees |
| `POST` | `/api/employees` | Create an employee |
| `PATCH` | `/api/employees/{id}` | Update, deactivate, or reactivate an employee |
| `GET` | `/api/employees/{id}/availability` | List weekly availability |
| `POST` | `/api/employees/{id}/availability` | Add weekly availability |
| `PATCH` | `/api/availability/{id}` | Update weekly availability |
| `DELETE` | `/api/availability/{id}` | Delete weekly availability |
| `GET` / `POST` | `/api/skills` | List or create catalog skills |
| `GET` / `POST` | `/api/employees/{id}/skills` | List or assign employee skills |
| `DELETE` | `/api/employees/{id}/skills/{skill_id}` | Remove an employee skill |
| `GET` | `/api/time-off` | List and filter time-off requests |
| `GET` / `POST` | `/api/employees/{id}/time-off` | List or submit employee time off |
| `PATCH` | `/api/time-off/{id}/decision` | Approve or reject pending time off |
| `GET` | `/api/shifts` | List and filter schedules |
| `POST` | `/api/shifts/recommendations` | Generate and save a draft schedule |
| `GET` | `/api/shifts/{id}` | Retrieve a draft or decided schedule |
| `PATCH` | `/api/shifts/{id}/decision` | Manager approval or rejection |
| `GET` | `/api/reports/schedules.pdf` | Download filtered schedules as PDF |
| `GET` | `/api/reports/schedules.xlsx` | Download filtered schedules as Excel |
| `GET` | `/api/reports/analytics.pdf` | Download analytics as PDF |
| `GET` | `/api/reports/analytics.xlsx` | Download analytics as Excel |

`day_of_week` uses `0` for Monday through `6` for Sunday. Overnight shifts are
outside this first MVP and are rejected explicitly.

Schedule-list filters are `date_from`, `date_to`, `required_role`,
`required_department`, `status`, and `employee_id`. Recommendation requests
may add `required_department` and a unique `required_skills` string array.
Responses include a persisted `constraint_summary` and human-readable
`constraint_warnings`. See `docs/openapi.yaml` for the authoritative request
and response contract.

`model_strategy` accepts `random_forest`, `gradient_boosting`,
`linear_regression`, or `auto`. Confidence ranges are operational uncertainty
estimates derived from cross-validated historical errors; they are not
statistical guarantees.

## Responsible-use boundaries

- Recommendations never become final schedules automatically.
- The API records who approved or rejected a recommendation.
- Overtime is excluded unless the caller explicitly sets `allow_overtime`.
- Even when overtime is enabled, an employee's `max_overtime_hours` is a hard
  weekly ceiling.
- Pending and approved time-off requests block assignments on matching dates.
- Rest and consecutive-day defaults are configurable operating safeguards, not
  a substitute for configuring applicable labor agreements and local law.
- The score uses operational data only; it does not use protected personal
  characteristics or hourly pay.
- A production version still needs authentication, authorization, encrypted
  deployment, formal database migrations, monitoring, and bias evaluation.


