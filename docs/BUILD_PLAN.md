# Build plan

One milestone per session, in this order. Each starts with a plan you approve, then the acceptance tests, then the code.

## M0 · Skeleton (Module 5)

Goal: An empty app in the confirmed stack that starts, reads its settings from .env, and has one passing test.

Acceptance tests:
- The health route returns ok
- The test command passes
- .env is in .gitignore
- blueprint.json is unchanged

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M0: Skeleton.
This folder holds only the build pack so far. If AGENTS.md says the stack is a DRAFT, stop and tell me.
Goal: An empty app in the confirmed stack that starts, reads its settings from .env, and has one passing test.
Read also: blueprint.json, docs/STACK.md, docs/ARCHITECTURE.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M1 · Authentication

Goal: People sign in with the methods in docs/AUTH.md, from a proven library or service.

Acceptance tests:
- A signed-out request to a private page is refused
- Sign-in and sign-out work in the provider's test mode
- No password is stored in plain text, and no session token appears in a log
- Sign-in works with: Email magic link
- Sign-in works with: Google sign-in
- An unverified email address cannot use the app
- Repeated failed sign-ins are slowed down, then locked for a while
- An owner or admin must pass two-factor sign-in

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M1: Authentication.
Milestones before M1 are done and their tests pass.
Goal: People sign in with the methods in docs/AUTH.md, from a proven library or service.
Read also: docs/AUTH.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M2 · Authorization and tenants

Goal: Every business is a tenant and every user has a role; every route checks the role against the permission matrix in docs/AUTH.md, and denies by default.

Acceptance tests:
- Customer A cannot read or change customer B's records, on every table
- A route with no permission rule is refused
- Only a role allowed to manage the team can change a role
- A Pharmacist/health care professional is refused: barcode scanner, Medicine Information Lookup, Medicines details page, Manage team and roles, Billing and plan, Business settings, Usage and logs, Export data
- A Guest User is refused: barcode scanner, Medicine Information Lookup, Medicines details page, Manage team and roles, Billing and plan, Business settings, Usage and logs, Export data
- A System Administrator is refused: barcode scanner, Medicine Information Lookup, Medicines details page, Manage team and roles, Billing and plan, Business settings, Usage and logs, Export data

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M2: Authorization and tenants.
Milestones before M2 are done and their tests pass.
Goal: Every business is a tenant and every user has a role; every route checks the role against the permission matrix in docs/AUTH.md, and denies by default.
Read also: docs/AUTH.md, docs/DATA_MODEL.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M3 · Data model and version 1 features

Goal: The tables in docs/DATA_MODEL.md and the version 1 features in docs/REQUIREMENTS.md, until their tests in the acceptance folder pass.

Acceptance tests:
- Every table has a tenant id, and every query filters by it
- Every acceptance test of “barcode scanner” passes (tests/acceptance/test_f1_barcode_scanner.py)
- Every acceptance test of “Medicine Information Lookup” passes (tests/acceptance/test_f2_medicine_information_lookup.py)
- Every acceptance test of “Medicines details page” passes (tests/acceptance/test_f3_medicines_details_page.py)

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M3: Data model and version 1 features.
Milestones before M3 are done and their tests pass.
Goal: The tables in docs/DATA_MODEL.md and the version 1 features in docs/REQUIREMENTS.md, until their tests in the acceptance folder pass.
Read also: docs/REQUIREMENTS.md, docs/DATA_MODEL.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M6 · Quality targets (Module 4)

Goal: Each target in docs/QUALITY.md has a test or a scripted check that passes.

Acceptance tests:
- Security: Every input is validated on the server
- Security: Secrets live only in environment variables, never in code, logs or the browser
- Security: HTTPS only, secure cookies and CSRF protection
- Security: Rate limits on sign-in and on every public route
- Security: A dependency audit runs on every build (pip-audit or npm audit)
- Security: Reviewed against the OWASP Top 10 before launch
- Reliability: Every error gives a clear message, and nothing is left half-saved
- Reliability: Calls to outside services time out and retry with back-off
- Reliability: Daily backups, restored once to prove they work
- Reliability: Payments and actions are idempotent: a retry never runs them twice
- Performance: p95 page load under 2 seconds on a phone over 4G
- Performance: p95 API response under 500 ms, not counting AI calls
- Performance: A database index for every list and search

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M6: Quality targets.
Milestones before M6 are done and their tests pass.
Goal: Each target in docs/QUALITY.md has a test or a scripted check that passes.
Read also: docs/QUALITY.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M7 · SaaS business

Goal: Plans with limits, billing in the provider's test mode, data retention, and the launch checklist in docs/ARCHITECTURE.md.

Acceptance tests:
- A payment webhook is verified before a plan changes
- Usage over the plan's limit is refused with an upgrade message
- Personal data older than 90 days is deleted or anonymised
- The privacy notice says what you collect, why and for how long
- Sign-up asks the customer to accept the terms
- A new customer can sign up and finish a first task without help
- The support channel is shown on every page

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M7: SaaS business.
Milestones before M7 are done and their tests pass.
Goal: Plans with limits, billing in the provider's test mode, data retention, and the launch checklist in docs/ARCHITECTURE.md.
Read also: docs/ARCHITECTURE.md, docs/PRICING.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

## M8 · Deploy and launch

Goal: Running on the internet over HTTPS, with backups, monitoring and a pricing page.

Acceptance tests:
- The live site answers over HTTPS
- A backup is restored once, to prove it works
- An uptime alert reaches your phone

Done when: `pytest -q` passes with these tests, and you have tried it by hand once.

Prompt for the session:
```text
Read AGENTS.md, then docs/BUILD_PLAN.md, milestone M8: Deploy and launch.
Milestones before M8 are done and their tests pass.
Goal: Running on the internet over HTTPS, with backups, monitoring and a pricing page.
Read also: docs/ARCHITECTURE.md, docs/QUALITY.md.

First, plan: list the files you will create or change and the acceptance tests you will add or fill in. Wait for my approval.
Then write the acceptance tests and show me that they fail. Then write the code until `pytest -q` passes.
Do not change blueprint.json or an acceptance test to make it pass. Do not start the next milestone.
At the end, show me the diff and the test output. Then run /verify. Do not commit until I say so.
```

Finish (you, as in Module 5):
1. Run `pytest -q` yourself, in a terminal.
2. Run `git status`: no .env or other secret file may be listed.
3. Read the diff (/verify help), and explain every changed line to yourself.
4. Commit one clear change, then record the evidence in GigaLab’s Build guide.

(M4 and M5 are skipped: no feature uses AI.)

## Before the first customer
- A privacy notice (PDPA)
- Terms of service
- Sign-up and a guided first task
- A support channel: email or WhatsApp
- Daily backups, restored once
- Uptime monitoring with an alert to your phone
- Not planned yet: Product analytics, without personal data.
- Three customers you have spoken to, who agreed to try it.
