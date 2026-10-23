# Using and running CODE4CARE

## Local development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then set APP_SECRET
python -m scripts.seed_demo        # optional: a demo pharmacy and catalogue
uvicorn app.main:app --reload
```

Open http://localhost:8000 and sign in with `pemilik@farmasi-demo.my`. In
development the sign-in page shows a **one-click sign-in** panel for every account
in the local database (`/dev/login`), so there is no e-mail and no second factor to
chase. That panel and route appear when `ENVIRONMENT=development` or
`DEMO_SIGN_IN=1`; tests assert they are absent in `testing` and in a plain
`production` (both demo flags unset).

If you use the normal form instead: in development the e-mail is printed to the
console and the "check your e-mail" page also shows the magic link, so the flow is
followable without a mail provider. Owners still pass the two-factor step there —
that is the production path, not a bug.

Useful addresses:

| Page | URL |
|---|---|
| Sign in | `/login` |
| Barcode scanner | `/scan` |
| Medicine lookup | `/scan` (one box for code, name or camera) |
| Scan history | `/history` |
| Import catalogue (Excel/CSV) | `/catalog/import` |
| Medicine pictures (upload on the page, or a ZIP on the import page) | `/medicines/<id>`, `/catalog/import` |
| Test labels (printable barcode + QR) | `/labels/test` |
| Team and roles | `/team` |
| Usage and logs | `/usage` |
| Export scans | `/export/scans.csv` |
| Health check | `/health` |

## Tests

```bash
pytest -q
```

The suite covers the skeleton (M0), authentication (M1), authorization and tenants
(M2), the three version 1 features (M3) and the quality targets (M6).

## Configuration (.env, never committed)

| Variable | Purpose |
|---|---|
| `APP_SECRET` | Signs CSRF and OAuth state values; required |
| `DATABASE_PATH` | SQLite file, default `data/code4care.db` |
| `ENVIRONMENT` | `development`, `testing` or `production` |
| `DEMO_SIGN_IN` | `1` shows the one-click sign-in panel in any environment; off when unset |
| `DEMO_AUTO_SIGN_IN` | `1` signs the demo owner in on every page, so the sign-in page is skipped; off when unset |
| `BASE_URL` | Public URL, used in magic links and the Google redirect |
| `EMAIL_API_KEY` | Email provider key; empty means print to the console |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `PAYMENT_API_KEY`, `PAYMENT_WEBHOOK_SECRET` | Stripe (milestone M7) |
| `SUPPORT_EMAIL`, `SUPPORT_WHATSAPP` | Support channel shown on every page |

Production refuses to start when `APP_SECRET` is empty or a placeholder.

## Backups

```bash
python -m scripts.backup --source data/code4care.db --destination backups/
python -m scripts.restore --backup backups/code4care-YYYYmmddTHHMMSSZ.db --target /tmp/restored.db
```

Medicine pictures are files outside the database, so include them:

```bash
python -m scripts.backup --source data/code4care.db --destination backups/ \
    --media data/medicine-images
python -m scripts.restore --backup backups/code4care-....db \
    --media-zip backups/code4care-....db.media.zip --media-target data/medicine-images
```

Both scripts verify with `PRAGMA integrity_check`. Restore into a scratch file
first, compare row counts, then restore over the live file with the app stopped.
Run the backup daily from cron and keep at least 14 days.

## Deploy (one VPS, Docker)

```bash
docker compose up -d --build
```

The compose file runs the app behind the published port; terminate TLS in front
of it (Caddy or nginx with Let's Encrypt) and forward `X-Forwarded-Proto`.
The app redirects any non-HTTPS request and sends HSTS, so TLS must be terminated
before the request reaches the app.

### Demo box: no sign-in step

A deployed demo should behave like the local one, so the compose file sets both
demo flags:

- `DEMO_SIGN_IN=1` shows the one-click panel for every account in the database,
  even under `ENVIRONMENT=production`. `/login` stays reachable, so you can switch
  account or log out.
- `DEMO_AUTO_SIGN_IN=1` opens a session for the demo pharmacy's owner on every page
  except `/login`, `/logout`, `/auth/*` and `/static/*`. The app never stops at the
  sign-in page. With no account in the database yet, run
  `docker compose exec app python -m scripts.seed_demo` once.

Anyone who can open the URL is signed in as the owner, so use this only with a demo
database. Before real pharmacy data lives on the server, set `DEMO_SIGN_IN=0` and
`DEMO_AUTO_SIGN_IN=0` in `.env`, run `docker compose up -d --build`, and the normal
sign-in page and its permission checks come back. The permission matrix still
applies to whoever signs in; the flags only decide how someone signs in, not what
they may do.

## What is built

- M0 skeleton, M1 sign-in (magic link, Google, verification, lockout, two-factor),
  M2 roles and tenant isolation, M3 the three version 1 features.
- M6 quality targets: validation, secrets, HTTPS/CSRF, rate limits, dependency
  audit wiring, OWASP review, error handling, outbound timeouts, backups,
  idempotency, performance budgets and indexes.

Not built yet: M7 (plans, Stripe billing, retention job, sign-up) and M8 (live
HTTPS deploy, uptime alerts). The pages for billing and settings explain the
current state instead of pretending to charge.
