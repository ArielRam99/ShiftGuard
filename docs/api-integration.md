# ShiftGuard AI API integration guide

The authoritative machine-readable contract is [`openapi.yaml`](openapi.yaml).
It describes the behavior implemented by the Flask application on `main`.

## Integration boundary

Frontend code communicates with ShiftGuard only through the HTTP API. It must
not read the SQLite database, import backend Python modules, or invoke the
scikit-learn model directly.

The current local base URL is `http://127.0.0.1:5000`. Current endpoint paths
start with `/api`.

## Manager workflow

1. Create employees with `POST /api/employees`.
2. Update, deactivate, or configure employee department, overtime, rest, and
   consecutive-day limits with `PATCH /api/employees/{employee_id}`.
3. Maintain the skill catalog through `GET/POST /api/skills`, then list or
   assign employee skills through `/api/employees/{employee_id}/skills`.
4. Add recurring availability, optionally setting `preference: preferred`, with
   `POST /api/employees/{employee_id}/availability`.
5. List availability with `GET /api/employees/{employee_id}/availability`,
   and maintain it with `PATCH` or `DELETE /api/availability/{availability_id}`.
6. Submit time off through `POST /api/employees/{employee_id}/time-off`.
   Managers use filtered `GET /api/time-off` and
   `PATCH /api/time-off/{request_id}/decision`.
7. Request a draft with `POST /api/shifts/recommendations`, optionally adding
   `required_department` and `required_skills`.
8. Display the selected `model_source`, recommended staff, `staffing_range`,
   assignments, reasons, overtime values, `coverage_gap`,
   `constraint_summary`, and `constraint_warnings` for manager review.
9. Record the manager's final action with
   `PATCH /api/shifts/{shift_id}/decision`.
10. Retrieve a saved schedule with `GET /api/shifts/{shift_id}`, or populate a
   schedule view with filtered `GET /api/shifts` requests.

Recommendations never become final automatically. The frontend should not
present a `draft` schedule as approved, and it should show a clear warning when
`coverage_gap` or any `projected_overtime_hours` value is greater than zero.

`GET /api/shifts` accepts inclusive `date_from` and `date_to` values plus
case-insensitive `required_role` and `required_department`, plus `status` and
`employee_id` filters. Filters are combined with AND.

## Workforce-constraint behavior

Candidate eligibility is evaluated before ranking:

- active employee, matching role, optional department, and every required skill;
- a recurring availability interval covering the full shift;
- no pending or approved time-off request covering the shift date;
- no overlap or gap shorter than the employee's `minimum_rest_hours`;
- no run longer than `max_consecutive_days`;
- no overtime unless requested, and never more than `max_overtime_hours`.

Among eligible employees, ranking favors lower weekly utilization, fewer
approved shifts during the previous 28 days, preferred availability, and higher
proficiency in required skills. Hourly rate is not used. Exclusion counts are
persisted with each shift so later retrieval and report integrations can explain
coverage gaps. Defaults are operational safeguards and must be configured for
the applicable jurisdiction and labor agreement.

## Forecasting and reports

Use `GET /api/model/comparison` to show cross-validated MAE, RMSE, and R2 for
Random Forest, Gradient Boosting, and Linear Regression. Recommendation requests
may set `model_strategy` to one of those names or to `auto`; omitting it retains
the compatible Random Forest default.

The staffing range is a 95% operational error band based on historical
out-of-fold prediction errors. It helps managers plan for demand variability but
does not replace manager judgment.

Schedules and analytics can be downloaded from:

- `GET /api/reports/schedules.pdf`
- `GET /api/reports/schedules.xlsx`
- `GET /api/reports/analytics.pdf`
- `GET /api/reports/analytics.xlsx`

Report endpoints accept the schedule filters used by `GET /api/shifts`.

## Contract compatibility policy

Until an explicitly versioned replacement is introduced, `docs/openapi.yaml`
is the source of truth for the current `/api` interface.

The following changes are backward compatible:

- adding an optional request property;
- adding a response property that clients may safely ignore;
- adding an endpoint or an optional query parameter;
- adding a new error case without changing successful responses.

The following are breaking changes and require a new versioned API path, such
as `/api/v2`, plus a migration period:

- renaming or removing a path or JSON property;
- changing a property's type or meaning;
- making an optional request property required;
- removing an accepted enum value;
- changing a successful status code or response envelope.

When changing the API:

1. Update the Flask implementation, OpenAPI document, and tests together.
2. Add at least one contract test for the affected success and error response.
3. Ask the interface owner to review frontend-impacting changes.
4. Merge only after backend tests and frontend contract checks pass.

## Current MVP limitations

- Authentication and authorization are not implemented.
- `manager_name` is supplied by the client and is not an authenticated identity.
- Overnight shifts are rejected.
- Availability is recurring weekly; time off supplies date-specific exceptions.
- `training_records` and `coverage_gap` are returned when a recommendation is
  created, but are not returned by later shift retrieval or decision responses.
- Error responses use a single `error` string and may optionally include a
  `details` object.

These limitations are documented rather than hidden so frontend and backend
work can progress independently without relying on behavior that does not yet
exist.
