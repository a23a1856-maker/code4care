# Security review: OWASP Top 10 (2021)

Reviewed for CODE4CARE version 1 (barcode scanner, medicine lookup, medicines
details page) before launch. Each item records how the risk is handled in this
codebase and the test or check that proves it.

Status: Mitigated means a control is in place and covered by a test.
Status: Monitored means the control exists and operations keep watching it.

## A01 Broken access control

Status: Mitigated

- Every route declares a permission in `ROUTE_RULES` (`app/main.py`); a route with
  no rule is refused by `RequestPipeline` before the handler runs (deny by default).
- Roles and the matrix live in `app/permissions.py` and are asserted equal to
  `blueprint.json` in `tests/test_authorization.py`.
- Tenants are isolated in `app/db.py`: every query goes through `scoped()`, which
  refuses SQL that does not filter by `tenant_id`; tests prove A cannot read or
  change B's rows in every table (`tests/test_tenancy.py`).
- Another tenant's medicine id returns 404, not 403, so ids are not confirmed.

## A02 Cryptographic failures

Status: Mitigated

- No passwords are stored at all: sign-in is an emailed magic link or Google OAuth.
- Session tokens and one-time codes are stored only as SHA-256 hashes; the raw
  token exists only in the visitor's HttpOnly cookie.
- Cookies are HttpOnly, SameSite=Lax and Secure in production; HTTPS is enforced
  with a redirect and HSTS (`app/security.py`, `RequestPipeline`).
- Secrets come from environment variables only (`app/config.py`); `.env` is
  gitignored and never logged.

## A03 Injection

Status: Mitigated

- All SQL uses parameters. Table names in the few dynamic statements are checked
  against a fixed allowlist (`app/db.py`).
- Barcode input is validated against EAN-8/12/13 with a check digit before any
  query (`app/barcode.py`); free text is length-checked.
- Jinja autoescapes every template; a search term of `<script>` is rendered as
  text (covered in `test_security_validate`).
- The Content-Security-Policy forbids inline script, so an escaping mistake has
  no script to run.

## A04 Insecure design

Status: Mitigated

- Deny by default, on the server, on every request; the UI only hides what the
  server already refuses.
- Sign-in is rate limited per address and per email, then locked for 15 minutes
  after 5 failures (`auth_attempts`, `lock_time`).
- Owners and system administrators must pass a second factor.
- Verification of email ownership is required before any feature page works.

## A05 Security misconfiguration

Status: Mitigated

- `/docs`, `/redoc` and `/openapi.json` are disabled in production.
- Security headers are set on every response: CSP, X-Frame-Options, nosniff,
  Referrer-Policy, Permissions-Policy, HSTS in production.
- Errors return a clear message with a code, and never a stack trace or SQL.
- Configuration is validated at start-up: production refuses a placeholder
  `APP_SECRET`.

## A06 Vulnerable and outdated components

Status: Monitored

- Dependencies are pinned in `requirements.txt`.
- `pip-audit` runs on every build in `.github/workflows/ci.yml` (and locally via
  `scripts/audit.sh`); `test_security_deps` fails if that wiring disappears.
- Upgrade policy: patch versions monthly, security fixes within 7 days.

## A07 Identification and authentication failures

Status: Mitigated

- No password storage, so no credential stuffing against a password hash.
- Magic links are single use, expire after 15 minutes, and are stored hashed.
- Two-factor codes are single use, expire after 5 minutes, and lock the account
  after repeated failures.
- Google sign-in requires `email_verified` from the provider before a session is
  created.
- Sign-out deletes the session row on the server; replaying the old cookie fails.
- Sessions expire after 8 hours.

## A08 Software and data integrity failures

Status: Mitigated

- Payments and repeatable actions use idempotency keys (`idempotency_keys`,
  `scans.request_key`), so a retry cannot save twice.
- Payment webhooks will be verified against `PAYMENT_WEBHOOK_SECRET` before a plan
  changes (milestone M7); card data is never stored.
- The medicine catalogue records its source and verification state; unverified
  rows never show dosage or warnings.
- Backups are taken with SQLite's online backup API and checked with
  `PRAGMA integrity_check` before being trusted.

## A09 Security logging and monitoring failures

Status: Monitored

- One log line per request: method, route template, status, duration, tenant id.
  No query strings, no cookies, no email addresses, no message text.
- Failed sign-ins and authorization refusals are recorded in `auth_attempts` and
  `audit_log` (tenant scoped).
- Availability: uptime check with an alert to the operator's phone (M8).

## A10 Server-side request forgery

Status: Mitigated

- The app makes outbound requests only to three fixed, configured endpoints
  (email provider, Google token, Google userinfo). No user input supplies a URL.
- Outbound calls have a hard timeout and exponential back-off
  (`app/outbound.py`), and failures surface as a clear message with nothing saved.

## Personal data (PDPA)

- Collected: staff email, role, feature use (barcodes scanned, medicines opened).
- Purpose: access control, history, export, abuse prevention.
- Retention: 90 days, then deleted or anonymised; deletion on request.
- Logs contain no personal data and no message text.
- Breach plan: notify affected customers and the regulator as soon as the extent
  is known, within 72 hours of discovery.

## Before launch

- [x] Reviewed against the OWASP Top 10
- [x] Dependency audit wired into the build
- [x] HTTPS, secure cookies and CSRF covered by tests
- [x] Rate limits on sign-in and every public route
- [ ] Penetration test by a second pair of eyes (recommended before 10 customers)
