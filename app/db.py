"""SQLite storage. Every table carries a tenant id and every query filters by it.

The only deliberate exception is `get_user_by_email`, used at sign-in to find
the tenant a person belongs to: it is looked up by the globally unique email
address, before any tenant is known.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import permissions
from app.seed_data import CATALOGUE, barcode_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'trial',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    is_owner INTEGER NOT NULL DEFAULT 0,
    totp_secret TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    subject_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    succeeded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    barcode TEXT NOT NULL,
    name TEXT NOT NULL,
    brand TEXT NOT NULL DEFAULT '',
    active_ingredient TEXT NOT NULL DEFAULT '',
    strength TEXT NOT NULL DEFAULT '',
    dosage_form TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    uses TEXT NOT NULL DEFAULT '',
    dosage_instructions TEXT NOT NULL DEFAULT '',
    warnings TEXT NOT NULL DEFAULT '',
    side_effects TEXT NOT NULL DEFAULT '',
    storage TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, barcode)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    barcode TEXT NOT NULL,
    medicine_id INTEGER REFERENCES medicines(id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    found INTEGER NOT NULL DEFAULT 0,
    request_key TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medicine_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favourites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, user_id, medicine_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    key_hash TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, key_hash, window_start)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, key, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_tenants_tenant ON tenants(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_email ON users(tenant_id, email_normalized);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_user ON sessions(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_login_codes_tenant_user ON login_codes(tenant_id, user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_tenant_subject ON auth_attempts(tenant_id, subject_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_medicines_tenant_barcode ON medicines(tenant_id, barcode);
CREATE INDEX IF NOT EXISTS idx_medicines_tenant_name ON medicines(tenant_id, name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_medicines_tenant_ingredient ON medicines(tenant_id, active_ingredient COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_scans_tenant_created ON scans(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scans_tenant_user ON scans(tenant_id, user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_tenant_request ON scans(tenant_id, request_key) WHERE request_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_medicine_views_tenant_created ON medicine_views(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_favourites_tenant_user ON favourites(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_created ON audit_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rate_limits_tenant_key ON rate_limits(tenant_id, key_hash, window_start);
CREATE INDEX IF NOT EXISTS idx_idempotency_tenant ON idempotency_keys(tenant_id, key);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: str | Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release; ALTER TABLE keeps existing databases valid.
MEDICINE_ADDED_COLUMNS = {
    "side_effects": "TEXT NOT NULL DEFAULT ''",
    "storage": "TEXT NOT NULL DEFAULT ''",
    "category": "TEXT NOT NULL DEFAULT ''",
    "extra_json": "TEXT NOT NULL DEFAULT ''",
}


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(medicines)")}
    for column, ddl in MEDICINE_ADDED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE medicines ADD COLUMN {column} {ddl}")


def scoped(conn: sqlite3.Connection, sql: str, tenant_id: int, params: tuple = ()):
    """Run a query that must name tenant_id, passing it as the first parameter.

    Anything that forgets the tenant filter fails loudly instead of leaking.
    """
    if "tenant_id" not in sql.lower():
        raise ValueError("every query must filter by tenant_id")
    return conn.execute(sql, (tenant_id, *params)).fetchall()


def scoped_one(conn, sql: str, tenant_id: int, params: tuple = ()):
    rows = scoped(conn, sql, tenant_id, params)
    return rows[0] if rows else None


# --------------------------------------------------------------------------- tenants


def create_tenant(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next FROM tenants").fetchone()
    tenant_id = int(row["next"])
    conn.execute(
        "INSERT INTO tenants (id, tenant_id, name, plan, created_at) VALUES (?, ?, ?, 'trial', ?)",
        (tenant_id, tenant_id, name, utcnow()),
    )
    _seed_catalogue(conn, tenant_id)
    conn.commit()
    return tenant_id


def get_tenant(conn: sqlite3.Connection, tenant_id: int) -> dict | None:
    row = scoped_one(conn, "SELECT * FROM tenants WHERE tenant_id = ?", tenant_id)
    return dict(row) if row else None


def _seed_catalogue(conn: sqlite3.Connection, tenant_id: int) -> None:
    now = utcnow()
    for index, item in enumerate(CATALOGUE, start=1):
        conn.execute(
            """
            INSERT INTO medicines (
                tenant_id, barcode, name, brand, active_ingredient, strength,
                dosage_form, manufacturer, uses, dosage_instructions, warnings,
                verified, source, verified_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                barcode_for(tenant_id, index),
                item["name"],
                item["brand"],
                item["active_ingredient"],
                item["strength"],
                item["dosage_form"],
                item["manufacturer"],
                item["uses"],
                item["dosage_instructions"],
                item["warnings"],
                item["verified"],
                "Katalog rujukan CODE4CARE",
                now if item["verified"] else None,
                now,
                now,
            ),
        )


# ----------------------------------------------------------------------------- users


def create_user(
    conn: sqlite3.Connection,
    tenant_id: int,
    email: str,
    role: str = permissions.ROLE_REGISTERED,
    *,
    verified: bool = True,
    is_owner: bool = False,
) -> dict:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("a valid email address is required")
    if role not in permissions.ROLE_NAMES:
        raise ValueError(f"unknown role: {role}")
    if conn.execute(
        "SELECT 1 FROM users WHERE email_normalized = ?", (normalized,)
    ).fetchone():
        raise ValueError(f"email already in use: {email}")
    cursor = conn.execute(
        """
        INSERT INTO users (tenant_id, email, email_normalized, role, email_verified, is_owner, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, email.strip(), normalized, role, int(verified), int(is_owner), utcnow()),
    )
    conn.commit()
    user = get_user(conn, tenant_id, cursor.lastrowid)
    assert user is not None
    return user


def get_user(conn: sqlite3.Connection, tenant_id: int, user_id: int) -> dict | None:
    row = scoped_one(
        conn, "SELECT * FROM users WHERE tenant_id = ? AND id = ?", tenant_id, (user_id,)
    )
    return dict(row) if row else None


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    """Sign-in lookup by the globally unique email; no tenant is known yet."""
    row = conn.execute(
        "SELECT * FROM users WHERE email_normalized = ?", (email.strip().lower(),)
    ).fetchone()
    return dict(row) if row else None


def list_dev_accounts(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Development only: every account, so the sign-in page can offer one click.

    The route calling this refuses unless the environment is development.
    """
    rows = conn.execute(
        "SELECT id, tenant_id, email, role FROM users ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def list_users(conn: sqlite3.Connection, tenant_id: int) -> list[dict]:
    rows = scoped(conn, "SELECT * FROM users WHERE tenant_id = ? ORDER BY id", tenant_id)
    return [dict(row) for row in rows]


def set_user_role(conn: sqlite3.Connection, tenant_id: int, user_id: int, role: str) -> int:
    if role not in permissions.ROLE_NAMES:
        raise ValueError(f"unknown role: {role}")
    cursor = conn.execute(
        "UPDATE users SET role = ? WHERE tenant_id = ? AND id = ?",
        (role, tenant_id, user_id),
    )
    conn.commit()
    return cursor.rowcount


def mark_email_verified(conn: sqlite3.Connection, tenant_id: int, user_id: int) -> None:
    conn.execute(
        "UPDATE users SET email_verified = 1 WHERE tenant_id = ? AND id = ?",
        (tenant_id, user_id),
    )
    conn.commit()


# ------------------------------------------------------------------------- medicines


def list_medicines(conn: sqlite3.Connection, tenant_id: int) -> list[dict]:
    rows = scoped(conn, "SELECT * FROM medicines WHERE tenant_id = ? ORDER BY name", tenant_id)
    return [dict(row) for row in rows]


def get_medicine(conn: sqlite3.Connection, tenant_id: int, medicine_id: int) -> dict | None:
    row = scoped_one(
        conn,
        "SELECT * FROM medicines WHERE tenant_id = ? AND id = ?",
        tenant_id,
        (medicine_id,),
    )
    return dict(row) if row else None


def find_medicine_by_barcode(
    conn: sqlite3.Connection, tenant_id: int, barcode: str
) -> dict | None:
    row = scoped_one(
        conn,
        "SELECT * FROM medicines WHERE tenant_id = ? AND barcode = ?",
        tenant_id,
        (barcode,),
    )
    return dict(row) if row else None


def search_medicines(
    conn: sqlite3.Connection, tenant_id: int, query: str, limit: int = 25
) -> list[dict]:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    rows = scoped(
        conn,
        """
        SELECT * FROM medicines
        WHERE tenant_id = ?
          AND (name LIKE ? ESCAPE '\\' OR brand LIKE ? ESCAPE '\\'
               OR active_ingredient LIKE ? ESCAPE '\\' OR barcode LIKE ? ESCAPE '\\')
        ORDER BY name
        LIMIT ?
        """,
        tenant_id,
        (like, like, like, like, limit),
    )
    return [dict(row) for row in rows]


def update_medicine(
    conn: sqlite3.Connection, tenant_id: int, medicine_id: int, fields: dict
) -> int:
    allowed = {
        "name",
        "brand",
        "active_ingredient",
        "strength",
        "dosage_form",
        "manufacturer",
        "uses",
        "dosage_instructions",
        "warnings",
        "verified",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return 0
    assignments = ", ".join(f"{key} = ?" for key in updates)
    cursor = conn.execute(
        f"UPDATE medicines SET {assignments}, updated_at = ? WHERE tenant_id = ? AND id = ?",
        (*updates.values(), utcnow(), tenant_id, medicine_id),
    )
    conn.commit()
    return cursor.rowcount


IMPORT_FIELDS = (
    "name",
    "brand",
    "active_ingredient",
    "strength",
    "dosage_form",
    "manufacturer",
    "uses",
    "dosage_instructions",
    "warnings",
    "side_effects",
    "storage",
    "category",
    "extra_json",
)


def upsert_imported_medicine(
    conn: sqlite3.Connection,
    tenant_id: int,
    data: dict,
    *,
    verified: bool = False,
    source: str = "",
) -> str:
    """Create or update one catalogue row by barcode, inside the caller's transaction.

    Returns "created", "updated" or "unchanged". Importing without the verified
    flag never downgrades a row a pharmacist has already verified.
    """
    existing = find_medicine_by_barcode(conn, tenant_id, data["barcode"])
    values = {field: str(data.get(field) or "") for field in IMPORT_FIELDS}
    now = utcnow()

    if existing:
        changed = any(str(existing.get(field) or "") != values[field] for field in IMPORT_FIELDS)
        new_verified = 1 if verified else int(existing["verified"] or 0)
        new_source = source if (verified and source) else (existing["source"] or "")
        verified_at = now if verified else existing["verified_at"]
        conn.execute(
            f"""
            UPDATE medicines SET {", ".join(f"{field} = ?" for field in IMPORT_FIELDS)},
                verified = ?, source = ?, verified_at = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                *(values[field] for field in IMPORT_FIELDS),
                new_verified,
                new_source,
                verified_at,
                now,
                tenant_id,
                existing["id"],
            ),
        )
        return "updated" if changed else "unchanged"

    conn.execute(
        f"""
        INSERT INTO medicines (
            tenant_id, barcode, {", ".join(IMPORT_FIELDS)}, verified, source,
            verified_at, created_at, updated_at
        ) VALUES (?, ?, {", ".join("?" for _ in IMPORT_FIELDS)}, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            data["barcode"],
            *(values[field] for field in IMPORT_FIELDS),
            int(verified),
            source,
            now if verified else None,
            now,
            now,
        ),
    )
    return "created"


# ----------------------------------------------------------------------------- scans


def save_scan(
    conn: sqlite3.Connection,
    tenant_id: int,
    user_id: int,
    barcode: str,
    medicine_id: int | None,
    source: str,
    request_key: str | None = None,
) -> int:
    """Record a scan for this business. A repeated request key is a no-op."""
    if request_key:
        existing = scoped_one(
            conn,
            "SELECT id FROM scans WHERE tenant_id = ? AND request_key = ?",
            tenant_id,
            (request_key,),
        )
        if existing:
            return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO scans (tenant_id, user_id, barcode, medicine_id, source, found, request_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, user_id, barcode, medicine_id, source, int(medicine_id is not None), request_key, utcnow()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_scans(
    conn: sqlite3.Connection, tenant_id: int, user_id: int | None = None, limit: int = 50
) -> list[dict]:
    sql = """
        SELECT scans.*, medicines.name AS medicine_name
        FROM scans LEFT JOIN medicines ON medicines.id = scans.medicine_id
        WHERE scans.tenant_id = ?
    """
    params: tuple = ()
    if user_id is not None:
        sql += " AND scans.user_id = ?"
        params = (user_id,)
    sql += " ORDER BY scans.created_at DESC, scans.id DESC LIMIT ?"
    rows = scoped(conn, sql, tenant_id, (*params, limit))
    return [dict(row) for row in rows]


def delete_scan(conn: sqlite3.Connection, tenant_id: int, scan_id: int) -> int:
    cursor = conn.execute(
        "DELETE FROM scans WHERE tenant_id = ? AND id = ?", (tenant_id, scan_id)
    )
    conn.commit()
    return cursor.rowcount


# ------------------------------------------------------------------------ favourites


def add_favourite(
    conn: sqlite3.Connection, tenant_id: int, user_id: int, medicine_id: int
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO favourites (tenant_id, user_id, medicine_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (tenant_id, user_id, medicine_id, utcnow()),
    )
    conn.commit()
    return cursor.rowcount == 1


def remove_favourite(
    conn: sqlite3.Connection, tenant_id: int, user_id: int, medicine_id: int
) -> int:
    cursor = conn.execute(
        "DELETE FROM favourites WHERE tenant_id = ? AND user_id = ? AND medicine_id = ?",
        (tenant_id, user_id, medicine_id),
    )
    conn.commit()
    return cursor.rowcount


def list_favourites(
    conn: sqlite3.Connection, tenant_id: int, user_id: int | None = None
) -> list[dict]:
    sql = """
        SELECT favourites.*, medicines.name AS medicine_name, medicines.strength AS strength
        FROM favourites JOIN medicines ON medicines.id = favourites.medicine_id
        WHERE favourites.tenant_id = ?
    """
    params: tuple = ()
    if user_id is not None:
        sql += " AND favourites.user_id = ?"
        params = (user_id,)
    sql += " ORDER BY favourites.created_at DESC"
    rows = scoped(conn, sql, tenant_id, params)
    return [dict(row) for row in rows]


# --------------------------------------------------------------------- views, audit


def record_view(
    conn: sqlite3.Connection, tenant_id: int, user_id: int, medicine_id: int
) -> int:
    cursor = conn.execute(
        "INSERT INTO medicine_views (tenant_id, user_id, medicine_id, created_at) VALUES (?, ?, ?, ?)",
        (tenant_id, user_id, medicine_id, utcnow()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_audit(conn: sqlite3.Connection, tenant_id: int, limit: int = 100) -> list[dict]:
    rows = scoped(
        conn,
        "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
        tenant_id,
        (limit,),
    )
    return [dict(row) for row in rows]


def audit(
    conn: sqlite3.Connection,
    tenant_id: int,
    user_id: int | None,
    action: str,
    detail: str = "",
) -> None:
    conn.execute(
        "INSERT INTO audit_log (tenant_id, user_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (tenant_id, user_id, action, detail, utcnow()),
    )
    conn.commit()


def verify_medicine(
    conn: sqlite3.Connection, tenant_id: int, medicine_id: int, *, source: str
) -> bool:
    """Mark one medicine's information as checked by the business.

    Only a verified medicine shows uses, dose and warnings to staff and on a
    scan; the flag is what separates checked reference text from an import.
    """
    now = utcnow()
    cursor = conn.execute(
        """
        UPDATE medicines
           SET verified = 1, verified_at = ?, source = ?, updated_at = ?
         WHERE tenant_id = ? AND id = ?
        """,
        (now, source, now, tenant_id, medicine_id),
    )
    conn.commit()
    return cursor.rowcount > 0


# ----------------------------------------------------------------- rate limits etc.


def consume_rate_limit(
    conn: sqlite3.Connection,
    tenant_id: int,
    key_hash: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> tuple[bool, int]:
    """Fixed-window limiter in SQLite, so no state lives in the app's memory."""
    now = now or datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    window_start = epoch - (epoch % window_seconds)
    row = conn.execute(
        "SELECT count FROM rate_limits WHERE tenant_id = ? AND key_hash = ? AND window_start = ?",
        (tenant_id, key_hash, window_start),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO rate_limits (tenant_id, key_hash, window_start, count) VALUES (?, ?, ?, 1)",
            (tenant_id, key_hash, window_start),
        )
        conn.commit()
        return True, 0
    if row["count"] >= limit:
        conn.commit()
        return False, max(1, window_start + window_seconds - epoch)
    conn.execute(
        "UPDATE rate_limits SET count = count + 1 WHERE tenant_id = ? AND key_hash = ? AND window_start = ?",
        (tenant_id, key_hash, window_start),
    )
    conn.commit()
    return True, 0


def remember_idempotent(
    conn: sqlite3.Connection, tenant_id: int, key: str, endpoint: str
) -> bool:
    cursor = conn.execute(
        "INSERT OR IGNORE INTO idempotency_keys (tenant_id, key, endpoint, created_at) VALUES (?, ?, ?, ?)",
        (tenant_id, key, endpoint, utcnow()),
    )
    conn.commit()
    return cursor.rowcount == 1


# ---------------------------------------------------------------------- auth attempts


def record_auth_attempt(
    conn: sqlite3.Connection,
    tenant_id: int,
    subject_hash: str,
    kind: str,
    succeeded: bool,
) -> None:
    conn.execute(
        "INSERT INTO auth_attempts (tenant_id, subject_hash, kind, succeeded, created_at) VALUES (?, ?, ?, ?, ?)",
        (tenant_id, subject_hash, kind, int(succeeded), utcnow()),
    )
    conn.commit()


def lock_seconds_left(
    conn: sqlite3.Connection,
    tenant_id: int,
    subject_hash: str,
    threshold: int,
    window_seconds: int,
) -> int:
    """Failed attempts (5 by default) in the window lock the account for the window."""
    since = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat(
        timespec="seconds"
    )
    rows = scoped(
        conn,
        """
        SELECT created_at FROM auth_attempts
        WHERE tenant_id = ? AND subject_hash = ? AND succeeded = 0 AND created_at >= ?
        ORDER BY created_at
        """,
        tenant_id,
        (subject_hash, since),
    )
    if len(rows) < threshold:
        return 0
    oldest = datetime.fromisoformat(rows[0]["created_at"])
    unlock_at = oldest + timedelta(seconds=window_seconds)
    remaining = int((unlock_at - datetime.now(timezone.utc)).total_seconds())
    return max(0, remaining)


def clear_auth_attempts(
    conn: sqlite3.Connection, tenant_id: int, subject_hash: str, kind: str
) -> None:
    conn.execute(
        "DELETE FROM auth_attempts WHERE tenant_id = ? AND subject_hash = ? AND kind = ?",
        (tenant_id, subject_hash, kind),
    )
    conn.commit()


def delete_login_code(conn: sqlite3.Connection, tenant_id: int, code_id: int) -> None:
    """Used when the message could not be sent: nothing half-saved is left behind."""
    conn.execute(
        "DELETE FROM login_codes WHERE tenant_id = ? AND id = ?", (tenant_id, code_id)
    )
    conn.commit()


def count_rows(conn: sqlite3.Connection, tenant_id: int, table: str) -> int:
    allowed = {
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
    }
    if table not in allowed:
        raise ValueError(f"unknown table: {table}")
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE tenant_id = ?", (tenant_id,)).fetchone()
    return int(row["n"])


def catalogue_stats(conn: sqlite3.Connection, tenant_id: int) -> dict:
    """Small headline numbers for the dashboard, scoped to one business."""
    row = scoped_one(
        conn,
        """
        SELECT COUNT(*) AS medicines,
               COUNT(DISTINCT CASE WHEN category <> '' THEN category END) AS categories,
               SUM(CASE WHEN verified = 0 THEN 1 ELSE 0 END) AS unverified
        FROM medicines WHERE tenant_id = ?
        """,
        tenant_id,
    )
    scans = scoped_one(conn, "SELECT COUNT(*) AS n FROM scans WHERE tenant_id = ?", tenant_id)
    return {
        "medicines": int(row["medicines"] or 0) if row else 0,
        "categories": int(row["categories"] or 0) if row else 0,
        "unverified": int(row["unverified"] or 0) if row else 0,
        "scans": int(scans["n"] or 0) if scans else 0,
    }
