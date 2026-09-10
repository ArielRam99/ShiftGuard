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
- Department-aware assignment matching
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

  The expected output is `Loaded ShiftGuard demo data.` The command creates
  200 synthetic employees, with four employees assigned to each of the 50
  predefined roles, plus recurring availability and historical staffing data.
  Running it again is safe because existing seed records are ignored.

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

## Windows executable

The CI workflow builds a Windows distribution after the test job succeeds. To
download it, open a successful **ShiftGuard CI** run in the repository's
**Actions** tab and select the **ShiftGuard-Windows** artifact. Artifacts are
retained for 30 days.

Extract the downloaded ZIP, keep all extracted files together, and run
`ShiftGuard.exe`. ShiftGuard starts a local server at
`http://127.0.0.1:5000` and opens the dashboard in the default browser. Closing
the ShiftGuard console stops the server. Application data persists at
`%LOCALAPPDATA%\ShiftGuard\shiftguard.sqlite`.

On startup, the packaged application loads the 200 synthetic demo employees,
availability, and training history when its database contains no employees.
Existing employee data is never replaced or supplemented automatically.

The distribution uses PyInstaller's one-folder layout because scientific
Python dependencies require supporting DLLs alongside the executable. To build
the same artifact locally on Windows:

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --noconfirm shiftguard.spec
```

The runnable distribution is created at `dist\ShiftGuard`, with the executable
at `dist\ShiftGuard\ShiftGuard.exe`. The application still requires internet
access for the dashboard's externally hosted Tailwind CSS, Lucide icons, and
display fonts.

PyInstaller packing is disabled because packed Python bootloaders can trigger
antivirus heuristics. Capstone artifacts are unsigned, so Windows may show an
**Unknown publisher** or Microsoft Defender SmartScreen warning. Verify the
published SHA-256 checksum before running a downloaded release, and do not
bypass a malware detection for an unverified download.

### Publish a release

After a commit has passed review and has been merged into `main`, create and
push a semantic-version tag from that commit:

```powershell
git switch main
git pull --ff-only
git tag -a v1.0.0 -m "ShiftGuard v1.0.0"
git push origin v1.0.0
```

The **ShiftGuard Release** workflow retests the tagged source, builds and
smoke-tests the Windows distribution, then publishes a versioned ZIP with a
SHA-256 checksum on the repository's **Releases** page. Release tags must match
`vMAJOR.MINOR.PATCH`, such as `v1.0.0`. These capstone release artifacts are
unsigned and may trigger a Windows publisher or SmartScreen warning.

## Use the dashboard

Open `http://127.0.0.1:5000` while the Flask development server is running.
The **Schedule** view predicts staffing and ranks eligible employees. Choose
Auto, Random Forest, Gradient Boosting, or Linear Regression before generating
a draft, then approve or reject it with a manager name.

Shift requirements use managed role and department catalogs rather than free
text. ShiftGuard preloads 50 common workforce roles and a starter department
list; API administrators can add entries or deactivate entries that should no
longer be available for new employees and shifts. Existing employee values are
preserved and added to the catalogs during an upgrade.

A role is required and determines the initial employee candidate pool. The
department is optional: **Any department** considers every active employee with
the selected role, while a specific department excludes role-matched employees
assigned elsewhere. Department therefore changes recommendation eligibility;
it is not a display-only field. The historical staffing CSV remains demand
training data and does not define either catalog.

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
may add `required_department`.
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


