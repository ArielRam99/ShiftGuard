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
- Startup upgrades existing PR #8 databases without deleting accounts or
  employee records. The nullable employee link has a foreign key and unique
  index on both new and upgraded databases; repeated startup is safe.
