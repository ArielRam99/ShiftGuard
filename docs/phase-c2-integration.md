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
