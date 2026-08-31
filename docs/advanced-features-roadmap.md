# ShiftGuard AI advanced-features roadmap

This roadmap divides the requested production features into reviewable phases.
Each phase must update the implementation, OpenAPI contract, tests, and user
documentation together. Existing API behavior and interface work remain intact.

## Phase A — Forecasting and analytics

- [x] Compare Random Forest, Gradient Boosting, and Linear Regression.
- [x] Provide reproducible MAE, RMSE, and R2 metrics.
- [x] Support explicit model selection and automatic lowest-error selection.
- [x] Return and persist a 95% operational staffing range.
- [x] Export filtered schedules as PDF and formatted Excel.
- [x] Export scheduling and model analytics as PDF and formatted Excel.

## Phase B — Employee constraints and skills

- [ ] Preferred availability and employee time-off requests.
- [ ] Manager approval or rejection of time off.
- [ ] Employee skills and department requirements.
- [ ] Skill-aware assignment matching.
- [ ] Minimum-rest and consecutive-shift safeguards.
- [ ] Configurable weekly overtime ceilings and fairness warnings.

## Phase C — Authentication, RBAC, and production database

- [ ] Secure login and credential storage.
- [ ] Admin, manager, and employee permission tiers.
- [ ] Employee assigned-shift and swap-request workflows.
- [ ] Admin/manager CSV imports and schedule publishing.
- [ ] PostgreSQL configuration and formal migrations while retaining SQLite for
      local development and automated tests.

## Phase D — Notifications and calendars

- [ ] Notification outbox triggered only by schedule publication.
- [ ] SendGrid email and Twilio SMS adapters configured through environment
      secrets and disabled when credentials are absent.
- [ ] Retry, idempotency, and delivery audit behavior.
- [ ] Per-employee `.ics` exports compatible with Google Calendar and Outlook.

External providers must never be called by automated tests. AI recommendations
remain advisory, and a manager retains final approval and publication authority.
