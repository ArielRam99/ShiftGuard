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
2. Add recurring availability with
   `POST /api/employees/{employee_id}/availability`.
3. Request a draft with `POST /api/shifts/recommendations`.
4. Display the returned assignments, reasons, overtime values, and
   `coverage_gap` for manager review.
5. Record the manager's final action with
   `PATCH /api/shifts/{shift_id}/decision`.
6. Retrieve the saved schedule with `GET /api/shifts/{shift_id}`.

Recommendations never become final automatically. The frontend should not
present a `draft` schedule as approved, and it should show a clear warning when
`coverage_gap` or any `projected_overtime_hours` value is greater than zero.

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
- Employee availability is recurring weekly availability, not date-specific.
- `training_records` and `coverage_gap` are returned when a recommendation is
  created, but are not returned by later shift retrieval or decision responses.
- Error responses use a single `error` string and may optionally include a
  `details` object.

These limitations are documented rather than hidden so frontend and backend
work can progress independently without relying on behavior that does not yet
exist.
