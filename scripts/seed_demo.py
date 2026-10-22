"""Create a demo pharmacy so the app can be tried by hand.

    python -m scripts.seed_demo

Then run `uvicorn app.main:app --reload`, open http://localhost:8000, sign in with
the printed address and read the magic link from the console (development mode
prints the e-mail instead of sending it).
"""
from __future__ import annotations

import argparse

from app import db
from app.config import Settings
from app.permissions import ROLE_PHARMACIST, ROLE_REGISTERED

DEMO_OWNER = "pemilik@farmasi-demo.my"
DEMO_PHARMACIST = "farmasi@farmasi-demo.my"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a demo pharmacy")
    parser.add_argument("--name", default="Farmasi Demo Sihat")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    db.init_db(settings.database_path)
    conn = db.connect(settings.database_path)
    try:
        existing = db.get_user_by_email(conn, DEMO_OWNER)
        if existing:
            print(f"demo pharmacy already exists (tenant {existing['tenant_id']})")
            return 0
        tenant_id = db.create_tenant(conn, args.name)
        db.create_user(
            conn, tenant_id, DEMO_OWNER, ROLE_REGISTERED, verified=True, is_owner=True
        )
        db.create_user(conn, tenant_id, DEMO_PHARMACIST, ROLE_PHARMACIST, verified=True)
        catalogue = db.list_medicines(conn, tenant_id)
    finally:
        conn.close()

    print(f"created {args.name} (tenant {tenant_id}) with {len(catalogue)} medicines")
    print(f"owner:      {DEMO_OWNER}  (two-factor code arrives by e-mail)")
    print(f"pharmacist: {DEMO_PHARMACIST} (holds no feature permissions)")
    if catalogue:
        first = catalogue[0]
        print(f"try barcode: {first['barcode']}  ({first['name']})")
    print("start the app with: uvicorn app.main:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
