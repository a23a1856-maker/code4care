"""Tenant isolation: every table carries the tenant id and every query filters by it."""
from __future__ import annotations

import pytest

from tests.conftest import sign_in
from tests.helpers import count, csrf_token

TENANT_TABLES = [
    "tenants",
    "users",
    "sessions",
    "login_codes",
    "auth_attempts",
    "medicines",
    "scans",
    "medicine_views",
    "favourites",
    "audit_log",
    "rate_limits",
    "idempotency_keys",
]


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_every_table_has_a_tenant_id(world, table):
    columns = [row["name"] for row in world["conn"].execute(f"PRAGMA table_info({table})")]
    assert "id" in columns, table
    assert "tenant_id" in columns, table


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_every_table_is_indexed_for_its_tenant(world, table):
    indexes = world["conn"].execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
        (table,),
    ).fetchall()
    covering = [
        row["sql"] for row in indexes if row["sql"] and "tenant_id" in row["sql"].lower()
    ]
    assert covering, f"{table} needs an index that starts with tenant_id"


def test_scoped_queries_require_a_tenant_filter(world):
    from app import db

    with pytest.raises(ValueError):
        db.scoped(world["conn"], "SELECT * FROM scans WHERE barcode = ?", 1, ("x",))
    rows = db.scoped(world["conn"], "SELECT * FROM scans WHERE tenant_id = ?", 1, ())
    assert rows == []


def test_customer_a_cannot_read_customer_b_records(client, world):
    conn = world["conn"]
    tenant_a = world["tenants"]["a"]
    tenant_b = world["tenants"]["b"]

    # Put one row per table in tenant B.
    from app import auth, db

    b_user = world["users"]["owner_b"]
    token, csrf = auth.create_session(
        conn, tenant_id=tenant_b, user_id=b_user["id"], settings=client.app.state.settings
    )
    db.save_scan(conn, tenant_b, b_user["id"], "12345670", None, "camera")
    db.record_view(conn, tenant_b, b_user["id"], world["medicines"]["b"][0]["id"])
    db.add_favourite(conn, tenant_b, b_user["id"], world["medicines"]["b"][0]["id"])
    db.audit(conn, tenant_b, b_user["id"], "test.action", "b only")
    conn.commit()

    # The repository can only ever see tenant A's rows.
    assert all(row["tenant_id"] == tenant_a for row in db.list_scans(conn, tenant_a))
    assert all(row["tenant_id"] == tenant_a for row in db.list_users(conn, tenant_a))
    assert all(row["tenant_id"] == tenant_a for row in db.list_medicines(conn, tenant_a))
    assert all(row["tenant_id"] == tenant_a for row in db.list_favourites(conn, tenant_a))
    assert all(row["tenant_id"] == tenant_a for row in db.list_audit(conn, tenant_a))
    assert db.list_audit(conn, tenant_a) == []

    # Fetching a tenant B row while acting for tenant A returns nothing.
    assert db.get_medicine(conn, tenant_a, world["medicines"]["b"][0]["id"]) is None
    assert db.get_user(conn, tenant_a, b_user["id"]) is None

    _ = (token, csrf)


def test_customer_a_cannot_change_customer_b_records(client, world):
    conn = world["conn"]
    tenant_a = world["tenants"]["a"]
    tenant_b = world["tenants"]["b"]
    b_medicine = world["medicines"]["b"][0]

    before = conn.execute(
        "SELECT name, strength FROM medicines WHERE id = ?", (b_medicine["id"],)
    ).fetchone()
    from app import db

    changed = db.update_medicine(
        conn, tenant_a, b_medicine["id"], {"name": "Hacked", "strength": "999mg"}
    )
    assert changed == 0
    after = conn.execute(
        "SELECT name, strength FROM medicines WHERE id = ?", (b_medicine["id"],)
    ).fetchone()
    assert after["name"] == before["name"]
    assert after["strength"] == before["strength"]

    b_scan = db.save_scan(conn, tenant_b, world["users"]["owner_b"]["id"], "12345670", None, "camera")
    assert db.delete_scan(conn, tenant_a, b_scan) == 0
    assert count(conn, "scans", tenant_b) == 1


def test_routes_never_reveal_another_tenants_ids(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])

    other_medicine = world["medicines"]["b"][0]
    response = client.get(f"/medicines/{other_medicine['id']}")
    assert response.status_code == 404

    export = client.get("/export/scans.csv")
    assert export.status_code == 200
    assert "12345670" not in export.text

    page = client.get("/team")
    assert page.status_code == 200
    assert world["users"]["owner_b"]["email"] not in page.text


def test_export_contains_only_this_businesses_scans(client, world):
    from app import db

    conn = world["conn"]
    db.save_scan(
        conn, world["tenants"]["a"], world["users"]["owner_a"]["id"],
        world["medicines"]["a"][0]["barcode"], world["medicines"]["a"][0]["id"], "camera",
    )
    db.save_scan(
        conn, world["tenants"]["b"], world["users"]["owner_b"]["id"],
        world["medicines"]["b"][0]["barcode"], world["medicines"]["b"][0]["id"], "camera",
    )
    conn.commit()

    sign_in(client, world["users"]["owner_a"]["email"])
    export = client.get("/export/scans.csv")
    assert world["medicines"]["a"][0]["barcode"] in export.text
    assert world["medicines"]["b"][0]["barcode"] not in export.text


def test_tenant_ids_are_used_in_every_write(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    client.post(
        "/scan/lookup",
        data={
            "barcode": world["medicines"]["a"][0]["barcode"],
            "csrf_token": csrf_token(page.text),
        },
        headers={"HX-Request": "true"},
    )
    rows = world["conn"].execute(
        "SELECT tenant_id FROM scans UNION ALL SELECT tenant_id FROM audit_log"
    ).fetchall()
    assert rows
    assert all(row["tenant_id"] == world["tenants"]["a"] for row in rows)
