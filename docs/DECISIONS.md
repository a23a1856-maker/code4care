# Decisions

Each decision, what GigaLab suggested from the inputs, what was chosen and why.

## 2. Requirements

### Version 1
- Chosen: **The must-haves only**
- Suggested: The must-haves only. 3 must-have features first: the smallest product a customer will pay for. The should-haves come after real use.
- Options: The must-haves only; Must and should
- Why it matters: Version 1 should be the smallest product a customer will pay for. Every extra feature is more to build, test and support before anyone pays.

## 3. Tech stack

### Frontend
- Chosen: **Server pages with htmx**
- Suggested: Server pages with htmx. You read Python best: the server renders the pages and htmx updates parts of them, so nearly all the code is Python you can review.
- Options: Plain HTML, CSS and JavaScript; Server pages with htmx; React (with Vite); Vue (with Vite); Next.js (React)
- Why it matters: The pages your customers see. Choose what you can read: the agent writes it, you approve every change.

### Backend
- Chosen: **Python: FastAPI**
- Suggested: Python: FastAPI. GigaLab’s own stack: you have seen every part of it working in Modules 1–7.
- Options: Python: FastAPI; Python: Django; Node.js: Express; Node.js: Next.js route handlers
- Why it matters: Where the rules live: sign-in, permissions, the data and the model calls. Keys and checks belong here, never in the browser (Module 1).

### Hosting
- Chosen: **One server (VPS) with Docker**
- Suggested: One server (VPS) with Docker. You can run a Linux server: one VPS with Docker is the cheapest.
- Options: One server (VPS) with Docker; A hosting platform (PaaS); Vercel or another serverless host
- Why it matters: Pick what you can keep running at 3 a.m. Backups and monitoring matter more than the vendor.

### Database
- Chosen: **SQLite**
- Suggested: SQLite. About 0 tasks a month on one server: one SQLite file is enough to start.
- Options: SQLite; PostgreSQL; MySQL or MariaDB
- Why it matters: Pick the smallest database that fits your volume and your hosting. You can move up later, but moving data is work.

## 5. Core modules

### Tenancy
- Chosen: **One database, tenant id on every row and key**
- Suggested: One database, tenant id on every row and key. One database with the tenant id on every row and key is cheap and enough; your tests prove the isolation.
- Options: One database, tenant id on every row and key; A database per customer
- Why it matters: Every query and every key must say which customer it belongs to, or one customer will see another's data.

## 12. SaaS business

### Billing
- Chosen: **Stripe**
- Suggested: Stripe. Cards and online banking: compare Stripe with a Malaysian FPX gateway for the methods and fees you need.
- Options: Manual invoices at first; A Malaysian gateway with FPX; Stripe
- Why it matters: Let a payment provider hold card and bank details; you only keep its customer id. Compare the fees and recurring-billing support yourself.

### How long you keep personal data
- Chosen: **90 days**
- Suggested: 90 days. Long enough to handle a complaint or a refund; delete or anonymise after that (PDPA).
- Options: 30 days; 90 days; One year; Until the customer deletes it
- Why it matters: Malaysia's PDPA: collect only what you need, say why, keep it no longer than needed, protect it, and let people ask for their data.

## 13. Build pack (Module 5)

### Coding agent
- Chosen: **Claude Code**
- Suggested: Claude Code. The course used Claude Code (Module 5); the pack works with any agent that reads AGENTS.md.
- Options: Claude Code; OpenAI Codex; Cursor; GitHub Copilot; Gemini CLI; Another agent
- Why it matters: AGENTS.md works for most coding agents; CLAUDE.md and GEMINI.md import it, and Copilot gets a pointer to it. All are in the pack.
