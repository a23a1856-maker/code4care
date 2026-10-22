"""Tokens, CSRF protection, rate-limit keys and security headers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Form, Request

from app.config import Settings

SESSION_COOKIE = "c4c_session"
CSRF_COOKIE = "c4c_csrf"
PENDING_COOKIE = "c4c_pending"


class CSRFError(Exception):
    """Raised when a state-changing request has no valid CSRF token."""


def hash_token(token: str) -> str:
    """Session tokens and one-time codes are stored only as a SHA-256 hash."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def hash_subject(value: str, settings: Settings) -> str:
    """A keyed hash, so attempt counters never hold an email address in clear."""
    return hmac.new(
        settings.app_secret.encode("utf-8"),
        value.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)[: length + 8]


def _signature(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(value: str, secret: str) -> str:
    return f"{value}.{_signature(value, secret)}"


def unsign(value: str, secret: str) -> str | None:
    if not value or "." not in value:
        return None
    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(payload, secret)):
        return None
    return payload


def new_csrf_value(secret: str) -> str:
    return sign(secrets.token_urlsafe(24), secret)


def _b64encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def new_oauth_state(secret: str, ttl_seconds: int = 600) -> str:
    expires = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    return _b64encode(sign(f"{secrets.token_urlsafe(16)}.{expires}", secret))


def verify_oauth_state(state: str, secret: str) -> bool:
    decoded = _b64decode(state)
    if not decoded:
        return False
    payload = unsign(decoded, secret)
    if not payload:
        return False
    try:
        expires = int(payload.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return False
    return expires >= int(datetime.now(timezone.utc).timestamp())


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_key(request: Request, scope: str, settings: Settings) -> str:
    return hash_subject(f"{client_ip(request)}|{scope}", settings)


def _form_token(csrf_token: str | None) -> str | None:
    return csrf_token


async def verify_csrf(request: Request, csrf_token: str | None = Form(default=None)) -> None:
    """Every unsafe method must carry the session's (or the visitor's) CSRF token."""
    supplied = request.headers.get("x-csrf-token") or csrf_token
    session = getattr(request.state, "session", None)
    if session:
        expected = session["csrf_token"]
    else:
        expected = request.cookies.get(CSRF_COOKIE, "")
        if expected and unsign(expected, request.app.state.settings.app_secret) is None:
            expected = ""
    if not supplied or not expected or not hmac.compare_digest(str(supplied), str(expected)):
        raise CSRFError("missing or invalid CSRF token")


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
}


def apply_security_headers(response, settings: Settings) -> None:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
