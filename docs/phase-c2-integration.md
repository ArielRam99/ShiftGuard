# Phase C2 integration gate

PR #8 remains the authentication foundation. Phase C keeps its Flask-Login
accounts, email sign-in, HTML forms, Flask-WTF CSRF checks, and
`viewer`/`manager`/`admin` roles. The focused pull requests harden and extend
that implementation; they do not replace it.

## C2a: Browser session behavior

- The manager dashboard sends the CSRF token and same-origin session cookie on
  unsafe API requests.
- An expired API session returns the browser to `/login`.
- Login, setup, dashboard, and API responses use `Cache-Control: no-store`.
- Flask-Login strong session protection is enabled.

Do not publish an intermediate stack commit as a completed authentication
release. Review and test the complete stack before merging the first focused
pull request.

## C2b: Role permissions and viewer ownership

- Administrators retain all PR #8 permissions.
- Managers can operate schedules and workforce records but cannot change
  administrator-only reference catalogs or import training data.
- A viewer must be linked to one active employee and can access only that
  employee's record, availability, skills, time off, and approved shifts.
- New API endpoints fail closed until they are added to an explicit allowlist.
- Schedule and time-off decisions use the signed-in account's display name;
  client-supplied manager identity is not trusted.

## C2c: Safe setup and account provisioning

- PR #8's administrator form remains, but it now requires a private token from
  the local launcher and closes permanently after the first account.
- The setup page uses local CSS only and removes its token from browser history.
- `create-user` keeps PR #8's email, display name, and role prompts. Viewer
  accounts additionally require one unique active employee ID.
- `SHIFTGUARD_DATABASE` can select the packaged database when provisioning
  accounts from a source checkout.

## C2d: Audit and whole-stack release checks

- PR #9 remains the logging backend. C2d reuses its one rotating handler and
  adds structured endpoint, status, actor ID, and resource ID audit records.
- Passwords, setup tokens, emails, names, notes, request bodies, and raw URLs
  are excluded from audit records.
- Linux source and Windows package smoke tests exercise private setup, PR #8
  form login, CSRF rejection, CSV import, AI recommendations, approval,
  exports, and logout.
- Release tags must use semantic versions and point to commits already on
  `main`.
