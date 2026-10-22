# CODE4CARE: build pack

Made with GigaLab Module 8 (SaaS Builder Lab) on 2026-10-22. Stack: confirmed.

`blueprint.json` is the source of truth: every requirement, choice and target as data. The documents in `docs/` explain it, and the tests in the acceptance folder fail until each feature is built.

## Status: version 1 is built

Milestones M0–M3 and the M6 quality targets are implemented and their tests pass.
An extra module added after version 1 imports the medicine catalogue from Excel or
CSV — see `docs/CATALOG_IMPORT.md` (the sample files `catalog code4care.csv` and
`catalog code4care.xlsx` show the expected columns). `/labels/test` prints a
barcode and QR label per medicine for trying the scanner without a physical box —
see `docs/TEST_LABELS.md`. Medicine pictures are uploaded per medicine or as a ZIP
named by barcode — see `docs/MEDICINE_IMAGES.md`.
Start here:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set APP_SECRET
python -m scripts.seed_demo     # optional demo pharmacy
uvicorn app.main:app --reload   # http://localhost:8000
pytest -q
```

Read `docs/OPERATIONS.md` for the demo sign-in, the environment variables, backups,
the Docker deploy and what is deliberately left for M7 and M8.

1. Put these files in an empty folder and start a Git repository there (`git init`).
2. Copy `.env.example` to `.env` and fill it in. Never commit `.env`.
3. Open the folder in your coding agent:
   - Claude Code: run `claude` in the folder. It reads CLAUDE.md (which imports AGENTS.md) and `.claude/settings.json`. (your choice)
   - Codex and Cursor read AGENTS.md.
   - GitHub Copilot reads AGENTS.md and `.github/copilot-instructions.md`.
   - Gemini CLI reads GEMINI.md, which imports AGENTS.md.
   - Any other agent: start with “Read AGENTS.md first.”
4. Start with milestone M0 in `docs/BUILD_PLAN.md`: paste its prompt, approve the plan, check the tests.
5. One milestone per session. Record each one in GigaLab’s Build guide tab.
6. To change a requirement or the stack: change it in GigaLab, download the pack again, and copy the new `blueprint.json` and `docs/` over the old ones.
