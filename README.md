# ShiftGuard AI

ShiftGuard AI is a workforce-scheduling MVP that recommends staffing levels and employees while requiring manager approval for every generated schedule.

## What this MVP includes

- Flask JSON API for employees, preferred availability, skills, time off, and
  shift recommendations
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
- Even when overtime is enabled, an employee's `max_overtime_hours` is a hard
  weekly ceiling.
- Pending and approved time-off requests block assignments on matching dates.
- Rest and consecutive-day defaults are configurable operating safeguards, not
  a substitute for configuring applicable labor agreements and local law.
- The score uses operational data only; it does not use protected personal
  characteristics or hourly pay.
- A production version still needs authentication, authorization, encrypted
  deployment, formal database migrations, monitoring, and bias evaluation.
# ShiftGuard AI - Wiki Guide

## Overview of Functionality

### 1. Database Management & Initialization (`init_db`)
* **SQLite Setup:** Automatically checks for or creates a local database file (`shiftguard.db`) in your project folder.
* **Table Schema:** Establishes a structured table called `historical_shifts` containing columns for `day_of_week` (0–6), `workload_hours` (expected volume of work), and `actual_headcount` (staff needed).

### 2. User Interface & Dashboard (`index`)
* **Tailwind CSS Styling:** Renders a clean, modern web interface using lightweight utility classes for layout, input boxes, headers, and cards.
* **Dual-Card Layout:** Separates functionality into two distinct operational blocks: **CSV Data Upload** and **AI Headcount Prediction**.

### 3. Historical CSV Data Ingestion (`upload_csv`)
* **File Upload Route (`/upload-csv`):** Accepts multi-part file uploads specifically targeted at `.csv` formats.
* **Pandas Processing:** Reads the uploaded file into a Pandas DataFrame.
* **Column Validation & Filtering:** Inspects incoming columns to ensure the necessary schema (`day_of_week`, `workload_hours`, `actual_headcount`) is present, dropping or ignoring auxiliary data.
* **Database Persistence:** Bulk-appends the parsed rows straight into the SQLite database using `to_sql()`.

### 4. Machine Learning Staffing Prediction (`predict`)
* **Dynamic Training (`LinearRegression`):** Whenever a prediction is requested, the app queries the SQLite database, loads the historical dataset, and instantly trains a fresh Ordinary Least Squares (OLS) Linear Regression model using Scikit-learn.
* **Feature Inputs:** Takes user-defined parameters—specifically expected **workload hours** and the selected **day of the week** (0–6)—via a POST request form.
* **Prediction Logic:** Runs the input features through the trained model to calculate a projected staffing requirement.
* **Safety Bounds:** Rounds the decimal prediction to the nearest integer, guarantees a minimum staffing floor of at least 1 employee, and renders the recommendation back onto the dashboard UI.

### 5. Application Server Lifecycle (`__main__`)
* **Flask Development Server:** Automatically runs `init_db()` to guarantee the database is ready upon startup, then launches the Flask app in debug mode on port `5000`.

---

## How to Run Locally

Follow these step-by-step instructions to set up and run the application on your local machine:

### Step 1: Clone the Repository Locally
Clone the project repository to your local machine using Git:
```bash
git clone https://github.com/ArielRam99/ShiftGuard.git C:\repos\ShiftGuard
```

### Step 2: Open Your Project Folder
Navigate to your local project directory: 
C:\repos\ShiftGuard

### Step 3: Install Requirements for ShiftGuard

```bash
python -m pip install pandas
python -m pip install numpy
python -m pip install scikit-learn
python -m pip install Flask
```

### Step 4: Start the application locally
Navigate to your local project directory: C:\repos\ShiftGuard\
```bash
python app.py
```

### Step 5: Open the dashboard
Open your web browser, and go to the following address to use the dashboard:
```bash
http://127.0.0.1:5000
```

---

## How to Run Unit Tests Locally

Follow these steps to run the test suite (`tests.py`) on your local machine:

### Step 1: Install Requirements
Make sure the application dependencies from the [How to Run Locally](#step-3-install-requirements-for-shiftguard) section are installed:
```bash
python -m pip install pandas
python -m pip install numpy
python -m pip install scikit-learn
python -m pip install Flask
```

### Step 2: Navigate to the Project Directory
Navigate to your local project directory, where `tests.py` is located.

### Step 3: Run the Test Suite
Run the tests using Python's built-in `unittest` module:
```bash
python -m unittest -v tests.py
```
The `-v` flag runs the tests in verbose mode, printing the name and result of each test case.

### Step 4: Review the Results
A successful run will show `OK` at the end of the output, confirming that the database initialization, dashboard route, and prediction endpoint are all working as expected.
