"""Sessions, one-time sign-in codes, two-factor codes and lockout.

No passwords are stored anywhere: people sign in with an emailed magic link or
with Google, both of which use one-time codes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.security import hash_token, random_token

SESSION_TTL_SECONDS = 8 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def cookie_flags(settings: Settings) -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.is_production,
        "path": "/",
    }


def create_session(
    conn, tenant_id: int, user_id: int, settings: Settings
) -> tuple[str, str]:
    token = random_token(32)
    csrf = random_token(24)
    now = _now()
    conn.execute(
        """
        INSERT INTO sessions (tenant_id, user_id, token_hash, csrf_token, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            user_id,
            hash_token(token),
            csrf,
            _iso(now),
            _iso(now + timedelta(seconds=settings.session_ttl_seconds or SESSION_TTL_SECONDS)),
        ),
    )
    conn.commit()
    return token, csrf


def resolve_session(conn, token: str, settings: Settings) -> dict | None:
    """Look the session up by its hashed token, then load the user scoped to its tenant."""
    from app import db

    row = conn.execute(
        "SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),)
    ).fetchone()
    if row is None:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        return None
    if expires <= _now():
        conn.execute(
            "DELETE FROM sessions WHERE tenant_id = ? AND id = ?", (row["tenant_id"], row["id"])
        )
        conn.commit()
        return None
    session = dict(row)
    user = db.get_user(conn, session["tenant_id"], session["user_id"])
    if user is None:
        return None
    return {"session": session, "user": user}


def destroy_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    conn.commit()


# ------------------------------------------------------------------- one-time codes


def create_login_code(
    conn, tenant_id: int, user_id: int, purpose: str, ttl_seconds: int, code_length: int = 0
) -> tuple[str, int]:
    code = (
        f"{secrets.randbelow(10 ** code_length):0{code_length}d}"
        if code_length
        else random_token(32)
    )
    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO login_codes (tenant_id, user_id, purpose, code_hash, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            user_id,
            purpose,
            hash_token(code),
            _iso(now),
            _iso(now + timedelta(seconds=ttl_seconds)),
        ),
    )
    conn.commit()
    return code, int(cursor.lastrowid)


def find_login_code(conn, code: str, purpose: str) -> dict | None:
    """Find an unused, unexpired code by its hash; the caller checks the tenant."""
    row = conn.execute(
        """
        SELECT * FROM login_codes
        WHERE code_hash = ? AND purpose = ? AND used_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (hash_token(code), purpose),
    ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) <= _now():
        return None
    return dict(row)


def get_login_code(conn, tenant_id: int, code_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM login_codes WHERE tenant_id = ? AND id = ?", (tenant_id, code_id)
    ).fetchone()
    return dict(row) if row else None


def consume_login_code(conn, tenant_id: int, code_id: int) -> None:
    conn.execute(
        "UPDATE login_codes SET used_at = ? WHERE tenant_id = ? AND id = ?",
        (_iso(_now()), tenant_id, code_id),
    )
    conn.commit()


def bump_code_attempts(conn, tenant_id: int, code_id: int) -> int:
    conn.execute(
        "UPDATE login_codes SET attempts = attempts + 1 WHERE tenant_id = ? AND id = ?",
        (tenant_id, code_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT attempts FROM login_codes WHERE tenant_id = ? AND id = ?", (tenant_id, code_id)
    ).fetchone()
    return int(row["attempts"]) if row else 0


# ------------------------------------------------------------------------- two factor


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, at: float | None = None) -> str:
    """RFC 6238 TOTP, 30 second steps, six digits (stdlib only)."""
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded.upper())
    counter = int((at if at is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, code: str, at: float | None = None, window: int = 1) -> bool:
    if not code or not code.isdigit():
        return False
    now = at if at is not None else time.time()
    return any(
        hmac.compare_digest(totp_code(secret, now + step * 30), code)
        for step in range(-window, window + 1)
    )


# ---------------------------------------------------------------------------- emails


def send_magic_link(settings: Settings, emailer, user: dict, token: str) -> None:
    url = f"{settings.base_url.rstrip('/')}/auth/magic?token={token}"
    emailer.send(
        user["email"],
        "Pautan masuk CODE4CARE",
        (
            "Salam,\n\n"
            "Klik pautan di bawah untuk masuk ke CODE4CARE. Pautan ini sah selama 15 minit "
            "dan hanya boleh digunakan sekali.\n\n"
            f"{url}\n\n"
            "Jika anda tidak meminta pautan ini, abaikan e-mel ini.\n\n"
            "CODE4CARE"
        ),
    )


def send_two_factor_code(settings: Settings, emailer, user: dict, code: str) -> None:
    emailer.send(
        user["email"],
        "Kod pengesahan CODE4CARE",
        (
            "Salam,\n\n"
            f"Kod pengesahan sekali guna anda ialah {code}. Kod ini sah selama 5 minit.\n\n"
            "Jika anda tidak cuba masuk, tukar tetapan keselamatan akaun anda.\n\n"
            "CODE4CARE"
        ),
    )
