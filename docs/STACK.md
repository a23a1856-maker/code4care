# Stack

Confirmed by the human in GigaLab on 2026-10-22.

| Layer | Choice | Why |
|---|---|---|
| Frontend | Server pages with htmx | The server renders the pages and htmx updates parts of them; little JavaScript to review |
| Backend | Python: FastAPI | GigaLab's own stack: small, fast and typed; you add sign-in and an admin with libraries |
| Database | SQLite | One file on the server; enough for a few thousand tasks a month on one server with a lasting disk |
| Hosting | One server (VPS) with Docker | Cheapest; you look after updates, backups and HTTPS |
| Extras | none | |

## Commands
- Install: `pip install -r requirements.txt`
- Run the tests: `pytest -q`
- Run the app: `uvicorn app.main:app --reload`

## Who looks after it
- Reads best: Python. Team: Two to five people. Runs a Linux server: Yes. Live updates: Yes: live chat, a live inbox or notifications.
