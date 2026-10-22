"""CODE4CARE: routes, the deny-by-default pipeline and the app factory."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match, Mount

from app import auth, catalog_import, db, images, labels, permissions, security, ui
from app.barcode import InvalidBarcode, normalize_query, request_key, validate_barcode
from app.config import Settings
from app.emailer import build_emailer
from app.google import GoogleOAuthClient
from app.outbound import OutboundError
from app.permissions import (
    PERM_BILLING,
    PERM_DETAILS,
    PERM_EXPORT,
    PERM_LOOKUP,
    PERM_SCAN,
    PERM_SETTINGS,
    PERM_TEAM,
    PERM_USAGE,
    PUBLIC,
)
from app.security import CSRF_COOKIE, PENDING_COOKIE, SESSION_COOKIE, CSRFError

logger = logging.getLogger("code4care.request")
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")

# Every route, with the permission it needs. A route that is not listed here is
# refused by the pipeline: deny by default.
ROUTE_RULES: dict[str, str] = {
    "/static": PUBLIC,
    "/health": PUBLIC,
    "/": PUBLIC,
    "/login": PUBLIC,
    "/login/2fa": PUBLIC,
    "/dev/login": PUBLIC,
    "/auth/magic": PUBLIC,
    "/auth/google": PUBLIC,
    "/auth/google/callback": PUBLIC,
    "/logout": PUBLIC,
    "/privacy": PUBLIC,
    "/terms": PUBLIC,
    "/scan": PERM_SCAN,
    "/scan/lookup": PERM_SCAN,
    "/search": PERM_LOOKUP,
    "/lookup/barcode": PERM_LOOKUP,
    "/medicines/{medicine_id}": PERM_DETAILS,
    "/medicines/{medicine_id}/image": PERM_DETAILS,
    "/medicines/{medicine_id}/image/upload": PERM_SETTINGS,
    "/medicines/{medicine_id}/image/remove": PERM_SETTINGS,
    "/medicines/{medicine_id}/verify": PERM_SETTINGS,
    "/history": PERM_SCAN,
    "/favourites": PERM_SCAN,
    "/favourites/{medicine_id}": PERM_SCAN,
    "/favourites/{medicine_id}/remove": PERM_SCAN,
    "/labels/test": PERM_SCAN,
    "/team": PERM_TEAM,
    "/team/{user_id}/role": PERM_TEAM,
    "/catalog/import": PERM_SETTINGS,
    "/catalog/template.xlsx": PERM_SETTINGS,
    "/catalog/images": PERM_SETTINGS,
    "/billing": PERM_BILLING,
    "/settings": PERM_SETTINGS,
    "/usage": PERM_USAGE,
    "/export/scans.csv": PERM_EXPORT,
}

# (method, path) -> (limit, window seconds). Public routes are limited by address.
PUBLIC_RATE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/login"): (20, 300),
    ("POST", "/login/2fa"): (40, 300),
    ("POST", "/logout"): (30, 60),
}
DEFAULT_PUBLIC_LIMIT = (120, 60)
DEFAULT_PRIVATE_LIMIT = (120, 60)
RATE_LIMITED_MESSAGE = (
    "Terlalu banyak permintaan daripada peranti ini. Sila tunggu sebentar dan cuba lagi."
)
NO_PERMISSION_MESSAGE = (
    "Peranan anda tidak mempunyai kebenaran untuk tindakan ini. "
    "Hubungi pemilik perniagaan jika anda memerlukan akses."
)
SIGNED_OUT_MESSAGE = "Sesi anda telah tamat. Sila masuk semula untuk meneruskan."

TRUTHY_FORM_VALUES = {"1", "ya", "yes", "on", "true", "t"}


def _medicine_extra(medicine: dict | None) -> dict:
    """The imported catalogue's extra columns, as a dict (empty when absent)."""
    if not medicine:
        return {}
    try:
        extra = json.loads(medicine.get("extra_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return extra if isinstance(extra, dict) else {}


CATALOG_EXTRA_LABELS = {
    "how_to_take": "Cara mengambil",
    "reg_class": "Kelas pendaftaran",
    "reg_no": "No. pendaftaran",
    "holder": "Pemegang pendaftaran",
    "origin": "Negara asal",
    "pack_size": "Pembungkusan",
    "halal": "Status halal",
    "price": "Harga (RM)",
    "stock": "Stok",
    "expiry": "Tarikh luput",
    "notes": "Nota",
    "image": "Rujukan imej",
}


def _match_route(request: Request) -> tuple[str | None, object | None]:
    path = request.scope["path"]
    for route in request.app.router.routes:
        if isinstance(route, Mount):
            prefix = route.path.rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return route.path, route
            continue
        match, _child = route.matches(request.scope)
        if match in (Match.FULL, Match.PARTIAL):
            return route.path, route
    return None, None


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _csv_cell(value) -> str:
    """Stop a spreadsheet from treating catalogue text as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


class RequestPipeline(BaseHTTPMiddleware):
    """HTTPS, sessions, permissions, rate limits, CSRF cookie, headers, one log line."""

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        settings = self.settings
        request.state.user = None
        request.state.session = None
        request.state.tenant_name = ""
        request.state.csrf = ""
        request.state.conn = None
        tenant_scope = 0

        if settings.is_production:
            proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            if proto != "https":
                return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)

        template, _route = _match_route(request)
        if template is None:
            return self._finish(
                request, ui.render_error(request, 404, "not_found", "Halaman tidak dijumpai."),
                started, None, None,
            )

        rule = ROUTE_RULES.get(template)
        if rule is None:
            return self._finish(
                request,
                ui.render_error(request, 403, "forbidden", NO_PERMISSION_MESSAGE),
                started, None, None,
            )

        conn = db.connect(settings.database_path)
        request.state.conn = conn
        pending_cookie: str | None = None
        try:
            token = request.cookies.get(SESSION_COOKIE)
            resolved = auth.resolve_session(conn, token, settings) if token else None
            if resolved:
                request.state.session = resolved["session"]
                request.state.user = resolved["user"]
                tenant = db.get_tenant(conn, resolved["session"]["tenant_id"])
                request.state.tenant_name = tenant["name"] if tenant else ""
                tenant_scope = resolved["session"]["tenant_id"]

            if request.state.session:
                request.state.csrf = request.state.session["csrf_token"]
            else:
                existing = request.cookies.get(CSRF_COOKIE, "")
                if existing and security.unsign(existing, settings.app_secret):
                    request.state.csrf = existing
                else:
                    pending_cookie = security.new_csrf_value(settings.app_secret)
                    request.state.csrf = pending_cookie

            user = request.state.user
            if user and not user["email_verified"] and rule != PUBLIC:
                response = ui.render_error(
                    request, 403, "email_unverified",
                    "Sahkan alamat e-mel anda sebelum menggunakan CODE4CARE. "
                    "Buka pautan pengesahan yang dihantar ke e-mel anda.",
                )
                return self._finish(request, response, started, tenant_scope, pending_cookie)

            if rule != PUBLIC:
                if user is None:
                    return self._finish(
                        request, self._signed_out(request), started, 0, pending_cookie
                    )
                if not permissions.allowed(user["role"], rule):
                    db.audit(conn, user["tenant_id"], user["id"], "authz.denied", template)
                    response = ui.render_error(
                        request, 403, "forbidden", NO_PERMISSION_MESSAGE
                    )
                    return self._finish(request, response, started, tenant_scope, pending_cookie)

            limit, window = PUBLIC_RATE_LIMITS.get(
                (request.method, template),
                DEFAULT_PUBLIC_LIMIT if rule == PUBLIC else DEFAULT_PRIVATE_LIMIT,
            )
            key = security.rate_key(request, f"{request.method} {template}", settings)
            allowed, retry_after = db.consume_rate_limit(
                conn, tenant_scope, key, limit, window
            )
            if not allowed:
                response = ui.render_error(request, 429, "rate_limited", RATE_LIMITED_MESSAGE)
                response.headers["Retry-After"] = str(retry_after)
                return self._finish(request, response, started, tenant_scope, pending_cookie)

            try:
                response = await call_next(request)
            except Exception:
                conn.rollback()
                raise
            return self._finish(request, response, started, tenant_scope, pending_cookie)
        finally:
            conn.close()

    def _signed_out(self, request: Request):
        if request.method in ("GET", "HEAD"):
            target = request.url.path
            suffix = f"?next={quote(target)}" if target not in ("/", "") else ""
            return RedirectResponse(f"/login{suffix}", status_code=303)
        return PlainTextResponse(SIGNED_OUT_MESSAGE, status_code=401)

    def _finish(self, request, response, started: float, tenant_scope, new_csrf):
        if new_csrf:
            response.set_cookie(
                CSRF_COOKIE,
                new_csrf,
                httponly=True,
                samesite="lax",
                secure=self.settings.is_production,
                path="/",
            )
        security.apply_security_headers(response, self.settings)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        route = _match_route(request)[0] or "-"
        logger.info(
            "request method=%s route=%s status=%s ms=%s tenant=%s",
            request.method,
            route,
            response.status_code,
            elapsed_ms,
            tenant_scope if tenant_scope is not None else "-",
        )
        return response


# ------------------------------------------------------------------------ helpers


def _conn(request: Request):
    return request.state.conn


def _user(request: Request) -> dict:
    return request.state.user


def _csrf_error(request: Request, code: str):
    return ui.render_error(
        request, 403, code, "Permintaan tidak sah. Muat semula halaman dan cuba lagi."
    )


def _set_session(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        **auth.cookie_flags(settings),
    )


def _clear_pending(response: Response, settings: Settings) -> None:
    response.delete_cookie(PENDING_COOKIE, path="/", secure=settings.is_production, httponly=True)


def _set_pending(response: Response, value: str, settings: Settings) -> None:
    response.set_cookie(
        PENDING_COOKIE,
        value,
        max_age=settings.pending_cookie_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )


def _pending_identity(request: Request) -> tuple[int, int, int] | None:
    payload = security.unsign(
        request.cookies.get(PENDING_COOKIE, ""), request.app.state.settings.app_secret
    )
    if not payload or payload.count(":") != 2:
        return None
    parts = payload.split(":")
    if not all(part.isdigit() for part in parts):
        return None
    tenant_id, user_id, code_id = (int(part) for part in parts)
    return tenant_id, user_id, code_id


def _pending_value(tenant_id: int, user_id: int, code_id: int) -> str:
    return f"{tenant_id}:{user_id}:{code_id}"


def _start_pending(request: Request, user: dict) -> tuple[str, str]:
    """Create the emailed six-digit 2FA code and the pending-cookie value."""
    conn = _conn(request)
    settings = request.app.state.settings
    code, code_id = auth.create_login_code(
        conn, user["tenant_id"], user["id"], "2fa",
        ttl_seconds=settings.two_factor_ttl_seconds, code_length=6,
    )
    request.app.state.emailer.send(
        user["email"],
        "Kod pengesahan CODE4CARE",
        (
            "Salam,\n\n"
            f"Kod pengesahan sekali guna anda ialah {code}. Kod ini sah selama 5 minit.\n\n"
            "Jika anda tidak cuba masuk, abaikan e-mel ini dan hubungi kami.\n\nCODE4CARE"
        ),
    )
    return code, security.sign(
        _pending_value(user["tenant_id"], user["id"], code_id), settings.app_secret
    )


def _sign_in(request: Request, user: dict) -> tuple[str, dict]:
    conn = _conn(request)
    settings = request.app.state.settings
    token, csrf = auth.create_session(conn, user["tenant_id"], user["id"], settings)
    db.audit(conn, user["tenant_id"], user["id"], "auth.sign_in", user["role"])
    return token, {"csrf": csrf}


# ------------------------------------------------------------------------- factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db.init_db(settings.database_path)

    # Windows' registry reports .js as text/plain; browsers refuse to execute that.
    import mimetypes

    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")

    app = FastAPI(
        title="CODE4CARE",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.emailer = build_emailer(settings)
    app.state.google = GoogleOAuthClient(settings)

    app.mount("/static", StaticFiles(directory=str(ui.ROOT / "static")), name="static")
    app.add_middleware(RequestPipeline, settings=settings)

    @app.exception_handler(CSRFError)
    async def _csrf_handler(request: Request, exc: CSRFError):
        return _csrf_error(request, "csrf")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error route=%s type=%s", request.url.path, type(exc).__name__)
        return ui.render_error(
            request, 500, "server_error",
            "Maaf, berlaku masalah di pelayan. Tiada data disimpan. Sila cuba lagi.",
        )

    # ------------------------------------------------------------------ public pages

    @app.get("/health")
    def health():
        return JSONResponse({"status": "ok"})

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        user = _user(request)
        conn = _conn(request)
        recent = (
            db.list_scans(conn, user["tenant_id"], user["id"], limit=5) if user else []
        )
        stats = db.catalogue_stats(conn, user["tenant_id"]) if user else None
        return ui.render(request, "home.html", recent=recent, stats=stats)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        settings = request.app.state.settings
        accounts = db.list_dev_accounts(_conn(request)) if settings.dev_sign_in else []
        return ui.render(request, "login.html", dev_accounts=accounts)

    @app.post("/login", response_class=HTMLResponse, dependencies=[Depends(security.verify_csrf)])
    def login_submit(request: Request, email: str = Form(default="")):
        conn = _conn(request)
        settings = request.app.state.settings
        address = email.strip().lower()
        if not EMAIL_PATTERN.match(address):
            return ui.render(
                request, "login.html", status_code=422,
                error="Masukkan alamat e-mel yang sah, contohnya nama@farmasi.my.",
            )

        limit_key = security.hash_subject(f"login-email|{address}", settings)
        allowed, retry_after = db.consume_rate_limit(conn, 0, limit_key, 5, 900)
        if not allowed:
            response = ui.render(
                request, "login.html", status_code=429,
                error="Terlalu banyak cubaan untuk alamat ini. Sila cuba lagi kemudian.",
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        user = db.get_user_by_email(conn, address)
        magic_url = None
        if user is not None:
            code, code_id = auth.create_login_code(
                conn, user["tenant_id"], user["id"], "magic",
                ttl_seconds=settings.login_code_ttl_seconds,
            )
            try:
                auth.send_magic_link(settings, request.app.state.emailer, user, code)
            except OutboundError:
                logger.warning("magic link could not be sent")
                db.delete_login_code(conn, user["tenant_id"], code_id)
                return ui.render(
                    request, "login.html", status_code=503,
                    error="E-mel tidak dapat dihantar sekarang. Sila cuba sebentar lagi.",
                )
            if settings.dev_sign_in:
                magic_url = f"{settings.base_url.rstrip('/')}/auth/magic?token={code}"
        return ui.render(request, "login_sent.html", magic_url=magic_url)

    @app.get("/auth/magic", response_class=HTMLResponse)
    def magic_link(request: Request, token: str = ""):
        conn = _conn(request)
        settings = request.app.state.settings
        row = auth.find_login_code(conn, token, "magic")
        if row is None:
            db.record_auth_attempt(
                conn, 0, security.hash_subject(f"magic|{security.client_ip(request)}", settings),
                "magic", False,
            )
            return ui.render_error(
                request, 400, "invalid_link",
                "Pautan ini tidak sah atau telah tamat tempoh. Minta pautan baharu.",
                title="Pautan tidak sah",
            )
        user = db.get_user(conn, row["tenant_id"], row["user_id"])
        if user is None:
            return ui.render_error(
                request, 400, "invalid_link", "Pautan ini tidak sah.", title="Pautan tidak sah"
            )
        auth.consume_login_code(conn, user["tenant_id"], row["id"])
        if not user["email_verified"]:
            db.mark_email_verified(conn, user["tenant_id"], user["id"])
            user = db.get_user(conn, user["tenant_id"], user["id"])

        if permissions.needs_two_factor(user["role"], bool(user["is_owner"])):
            _code, pending = _start_pending(request, user)
            response = RedirectResponse("/login/2fa", status_code=303)
            _set_pending(response, pending, settings)
            return response

        token_value, _csrf = _sign_in(request, user)
        response = RedirectResponse("/", status_code=303)
        _set_session(response, token_value, settings)
        return response

    @app.get("/login/2fa", response_class=HTMLResponse)
    def two_factor_page(request: Request):
        if _pending_identity(request) is None:
            return RedirectResponse("/login", status_code=303)
        return ui.render(request, "two_factor.html")

    @app.post("/login/2fa", response_class=HTMLResponse, dependencies=[Depends(security.verify_csrf)])
    def two_factor_submit(request: Request, code: str = Form(default="")):
        conn = _conn(request)
        settings = request.app.state.settings
        pending = _pending_identity(request)
        if pending is None:
            return ui.render_error(
                request, 400, "pending_expired",
                "Sesi pengesahan telah tamat. Sila masuk semula.", title="Sesi tamat",
            )
        tenant_id, user_id, code_id = pending
        user = db.get_user(conn, tenant_id, user_id)
        session_code = auth.get_login_code(conn, tenant_id, code_id)
        if user is None or session_code is None or session_code["user_id"] != user["id"]:
            return ui.render_error(
                request, 400, "pending_expired",
                "Sesi pengesahan tidak sah. Sila masuk semula.", title="Sesi tamat",
            )

        subject = security.hash_subject(user["email"], settings)
        locked = db.lock_seconds_left(
            conn, tenant_id, subject, settings.lockout_threshold, settings.lockout_window_seconds
        )
        if locked:
            response = ui.render_error(
                request, 429, "locked",
                "Akaun dikunci sementara kerana terlalu banyak cubaan. "
                f"Cuba lagi dalam {max(1, locked // 60)} minit.",
                title="Akaun dikunci",
            )
            response.headers["Retry-After"] = str(locked)
            return response

        if session_code["used_at"] is not None:
            return ui.render_error(
                request, 400, "code_used",
                "Kod ini telah digunakan. Sila masuk semula untuk minta kod baharu.",
                title="Kod telah digunakan",
            )

        if not security.hash_token(code.strip()) == session_code["code_hash"] or not code.strip().isdigit():
            auth.bump_code_attempts(conn, tenant_id, code_id)
            db.record_auth_attempt(conn, tenant_id, subject, "2fa", False)
            locked = db.lock_seconds_left(
                conn, tenant_id, subject, settings.lockout_threshold, settings.lockout_window_seconds
            )
            if locked:
                response = ui.render_error(
                    request, 429, "locked",
                    "Akaun dikunci sementara kerana terlalu banyak cubaan. "
                    f"Cuba lagi dalam {max(1, locked // 60)} minit.",
                    title="Akaun dikunci",
                )
                response.headers["Retry-After"] = str(locked)
                return response
            return ui.render(request, "two_factor.html", status_code=403,
                             error="Kod pengesahan tidak betul. Sila cuba lagi.")

        auth.consume_login_code(conn, tenant_id, code_id)
        db.clear_auth_attempts(conn, tenant_id, subject, "2fa")
        db.record_auth_attempt(conn, tenant_id, subject, "2fa", True)
        token_value, _csrf = _sign_in(request, user)
        response = RedirectResponse("/", status_code=303)
        _set_session(response, token_value, settings)
        _clear_pending(response, settings)
        return response

    @app.get("/auth/google")
    def google_start(request: Request):
        settings = request.app.state.settings
        if not settings.google_client_id:
            return ui.render_error(
                request, 503, "google_unavailable",
                "Log masuk Google belum dikonfigurasikan. Sila guna pautan e-mel.",
                title="Google tidak tersedia",
            )
        state = security.new_oauth_state(settings.app_secret)
        return RedirectResponse(request.app.state.google.authorize_url(state), status_code=303)

    @app.get("/auth/google/callback", response_class=HTMLResponse)
    def google_callback(request: Request, code: str = "", state: str = ""):
        conn = _conn(request)
        settings = request.app.state.settings
        if not security.verify_oauth_state(state, settings.app_secret):
            return ui.render_error(
                request, 403, "oauth_state",
                "Permintaan log masuk Google tidak sah. Sila cuba lagi.",
                title="Log masuk gagal",
            )
        try:
            profile = request.app.state.google.exchange_code(code)
        except OutboundError:
            logger.warning("google token exchange failed")
            return ui.render_error(
                request, 503, "oauth_failed",
                "Google tidak dapat disahkan sekarang. Sila cuba lagi atau guna pautan e-mel.",
                title="Log masuk gagal",
            )

        address = str(profile.get("email", "")).strip().lower()
        if not profile.get("email_verified") or not EMAIL_PATTERN.match(address):
            return ui.render_error(
                request, 403, "email_unverified",
                "Alamat e-mel Google anda belum disahkan. Sahkan e-mel anda dahulu, "
                "kemudian cuba lagi.",
                title="E-mel belum disahkan",
            )

        user = db.get_user_by_email(conn, address)
        if user is None:
            return ui.render_error(
                request, 403, "no_account",
                "Tiada akaun CODE4CARE untuk alamat ini. Hubungi pemilik farmasi anda.",
                title="Tiada akaun",
            )

        subject = security.hash_subject(user["email"], settings)
        locked = db.lock_seconds_left(
            conn, user["tenant_id"], subject, settings.lockout_threshold,
            settings.lockout_window_seconds,
        )
        if locked:
            response = ui.render_error(
                request, 429, "locked",
                "Akaun dikunci sementara kerana terlalu banyak cubaan. Sila cuba kemudian.",
                title="Akaun dikunci",
            )
            response.headers["Retry-After"] = str(locked)
            return response

        if not user["email_verified"]:
            db.mark_email_verified(conn, user["tenant_id"], user["id"])
            user = db.get_user(conn, user["tenant_id"], user["id"])

        if permissions.needs_two_factor(user["role"], bool(user["is_owner"])):
            _code, pending = _start_pending(request, user)
            response = RedirectResponse("/login/2fa", status_code=303)
            _set_pending(response, pending, settings)
            return response

        token_value, _csrf = _sign_in(request, user)
        response = RedirectResponse("/", status_code=303)
        _set_session(response, token_value, settings)
        return response

    @app.post("/logout", dependencies=[Depends(security.verify_csrf)])
    def logout(request: Request):
        settings = request.app.state.settings
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            auth.destroy_session(_conn(request), token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.is_production, httponly=True)
        _clear_pending(response, settings)
        return response

    @app.post("/dev/login", dependencies=[Depends(security.verify_csrf)])
    def dev_login(request: Request, email: str = Form(default="")):
        """Development only: one click, no e-mail and no second factor."""
        settings = request.app.state.settings
        if not settings.dev_sign_in:
            return ui.render_error(request, 404, "not_found", "Halaman tidak dijumpai.")
        conn = _conn(request)
        user = db.get_user_by_email(conn, email.strip().lower())
        if user is None:
            return ui.render_error(
                request, 404, "not_found",
                "Tiada akaun pembangunan dengan e-mel itu. Jalankan python -m scripts.seed_demo.",
            )
        token_value, _csrf = _sign_in(request, user)
        response = RedirectResponse("/", status_code=303)
        _set_session(response, token_value, settings)
        return response

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request):
        return ui.render(request, "privacy.html")
    @app.get("/terms", response_class=HTMLResponse)
    def terms(request: Request):
        return ui.render(request, "terms.html")

    # ----------------------------------------------------------------- feature pages

    @app.get("/scan", response_class=HTMLResponse)
    def scan_page(request: Request):
        return ui.render(request, "scan.html")

    @app.get("/labels/test", response_class=HTMLResponse)
    def test_labels(request: Request, page: str = "1"):
        user = _user(request)
        medicines = db.list_medicines(_conn(request), user["tenant_id"])
        per_page = 24
        total = len(medicines)
        pages = max(1, (total + per_page - 1) // per_page)
        wanted = int(page) if page.isdigit() else 1
        current = min(max(1, wanted), pages)
        start = (current - 1) * per_page
        items = [labels.label_item(m) for m in medicines[start : start + per_page]]
        return ui.render(
            request, "test_labels.html", items=items, total=total,
            page=current, pages=pages,
        )

    @app.post(
        "/scan/lookup",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def scan_lookup(
        request: Request,
        barcode: str = Form(default=""),
        request_id: str = Form(default=""),
    ):
        conn = _conn(request)
        user = _user(request)
        medicine = None
        try:
            clean = validate_barcode(barcode)
        except InvalidBarcode as exc:
            # A QR label or an internal catalogue code is acceptable only when it
            # really exists in this business's catalogue; anything else is refused.
            try:
                candidate = catalog_import.normalise_product_code(barcode)
            except ValueError:
                candidate = ""
            medicine = (
                db.find_medicine_by_barcode(conn, user["tenant_id"], candidate)
                if candidate
                else None
            )
            if medicine is None:
                return ui.render(
                    request, "partials/scan_result.html", status_code=422,
                    error_code="invalid_barcode", error_message=str(exc),
                )
            clean = candidate

        if medicine is None:
            medicine = db.find_medicine_by_barcode(conn, user["tenant_id"], clean)
        scan_id = db.save_scan(
            conn, user["tenant_id"], user["id"], clean,
            medicine["id"] if medicine else None, "camera", request_key(request_id),
        )
        db.audit(conn, user["tenant_id"], user["id"], "scan.created", clean)
        settings = request.app.state.settings
        return ui.render(
            request, "partials/scan_result.html",
            scan_id=scan_id, barcode=clean, medicine=medicine,
            extra=_medicine_extra(medicine),
            has_image=bool(medicine) and images.has_image(
                settings, user["tenant_id"], medicine["id"]
            ),
            image_version=images.image_version(
                settings, user["tenant_id"], medicine["id"]
            ) if medicine else 0,
        )

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request):
        return ui.render(request, "search.html")

    @app.post(
        "/search", response_class=HTMLResponse, dependencies=[Depends(security.verify_csrf)]
    )
    def search_submit(request: Request, q: str = Form(default="")):
        conn = _conn(request)
        user = _user(request)
        try:
            clean = normalize_query(q)
        except InvalidBarcode as exc:
            return ui.render(
                request, "partials/lookup_result.html", status_code=422,
                error_code="invalid_lookup", error_message=str(exc), results=[],
            )
        results = db.search_medicines(conn, user["tenant_id"], clean)
        settings = request.app.state.settings
        with_images = {
            medicine["id"] for medicine in results
            if images.has_image(settings, user["tenant_id"], medicine["id"])
        }
        return ui.render(
            request, "partials/lookup_result.html", results=results,
            query=clean, with_images=with_images,
        )

    @app.post(
        "/lookup/barcode",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def lookup_barcode(
        request: Request,
        barcode: str = Form(default=""),
        query: str = Form(default=""),
        request_id: str = Form(default=""),
    ):
        conn = _conn(request)
        user = _user(request)
        generic_message = "Masukkan kod bar atau nama ubat yang sah."

        if barcode.strip():
            try:
                clean = validate_barcode(barcode)
            except InvalidBarcode as exc:
                return ui.render(
                    request, "partials/lookup_result.html", status_code=422,
                    error_code="invalid_lookup", error_message=str(exc), results=[],
                )
            medicine = db.find_medicine_by_barcode(conn, user["tenant_id"], clean)
            db.save_scan(
                conn, user["tenant_id"], user["id"], clean,
                medicine["id"] if medicine else None, "search", request_key(request_id),
            )
            db.audit(conn, user["tenant_id"], user["id"], "lookup.barcode", clean)
            settings = request.app.state.settings
            results = [medicine] if medicine else []
            with_images = {
                item["id"] for item in results
                if images.has_image(settings, user["tenant_id"], item["id"])
            }
            return ui.render(
                request, "partials/lookup_result.html",
                results=results, barcode=clean, with_images=with_images,
            )

        if query.strip():
            try:
                clean_query = normalize_query(query)
            except InvalidBarcode as exc:
                return ui.render(
                    request, "partials/lookup_result.html", status_code=422,
                    error_code="invalid_lookup", error_message=str(exc), results=[],
                )
            results = db.search_medicines(conn, user["tenant_id"], clean_query)
            return ui.render(
                request, "partials/lookup_result.html", results=results, query=clean_query
            )

        return ui.render(
            request, "partials/lookup_result.html", status_code=422,
            error_code="invalid_lookup", error_message=generic_message, results=[],
        )

    @app.get("/medicines/{medicine_id}", response_class=HTMLResponse)
    def medicine_page(request: Request, medicine_id: str):
        conn = _conn(request)
        user = _user(request)
        identifier = int(medicine_id) if medicine_id.isdigit() else 0
        medicine = (
            db.get_medicine(conn, user["tenant_id"], identifier) if identifier > 0 else None
        )
        if medicine is None:
            return ui.render_error(
                request, 404, "medicine_not_found",
                "Ubat tidak dijumpai dalam katalog perniagaan anda.",
                title="Ubat tidak dijumpai",
            )
        db.record_view(conn, user["tenant_id"], user["id"], medicine["id"])
        favourite = any(
            row["medicine_id"] == medicine["id"]
            for row in db.list_favourites(conn, user["tenant_id"], user["id"])
        )
        extra_items = []
        extra = _medicine_extra(medicine)
        for key, label in CATALOG_EXTRA_LABELS.items():
            value = extra.get(key)
            if value not in (None, ""):
                extra_items.append({"label": label, "value": value})
        settings = request.app.state.settings
        return ui.render(
            request, "medicine.html", medicine=medicine, favourite=favourite,
            extra_items=extra_items, extra=extra,
            has_image=images.has_image(settings, user["tenant_id"], medicine["id"]),
            image_version=images.image_version(settings, user["tenant_id"], medicine["id"]),
            can_manage=permissions.allowed(user["role"], PERM_SETTINGS),
        )

    # ---------------------------------------------------------- medicine images

    def _medicine_from_path(request: Request, medicine_id: str) -> dict | None:
        user = _user(request)
        identifier = int(medicine_id) if medicine_id.isdigit() else 0
        if identifier <= 0:
            return None
        return db.get_medicine(_conn(request), user["tenant_id"], identifier)

    def _image_panel(request: Request, medicine: dict, *, status_code: int = 200,
                     error: str | None = None, notice: str | None = None):
        settings = request.app.state.settings
        user = _user(request)
        return ui.render(
            request, "partials/medicine_image.html", status_code=status_code,
            medicine=medicine, error=error, notice=notice,
            has_image=images.has_image(settings, user["tenant_id"], medicine["id"]),
            image_version=images.image_version(settings, user["tenant_id"], medicine["id"]),
            can_manage=permissions.allowed(user["role"], PERM_SETTINGS),
        )

    @app.get("/medicines/{medicine_id}/image")
    def medicine_image(request: Request, medicine_id: str):
        medicine = _medicine_from_path(request, medicine_id)
        if medicine is None:
            return Response(status_code=404)
        payload = images.read_image(
            request.app.state.settings, medicine["tenant_id"], medicine["id"]
        )
        if payload is None:
            return Response(status_code=404)
        return Response(
            payload,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.post(
        "/medicines/{medicine_id}/image/upload",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    async def medicine_image_upload(
        request: Request, medicine_id: str, image: UploadFile | None = File(default=None)
    ):
        medicine = _medicine_from_path(request, medicine_id)
        if medicine is None:
            return ui.render_error(
                request, 404, "medicine_not_found", "Ubat tidak dijumpai.",
                title="Ubat tidak dijumpai",
            )
        if image is None or not image.filename:
            return _image_panel(
                request, medicine, status_code=422,
                error="Pilih fail gambar (JPG, PNG atau WebP) terlebih dahulu.",
            )
        payload = await image.read(images.MAX_UPLOAD_BYTES + 1)
        try:
            images.save_image(
                request.app.state.settings, medicine["tenant_id"], medicine["id"], payload
            )
        except images.InvalidImage as exc:
            return _image_panel(request, medicine, status_code=422, error=str(exc))

        user = _user(request)
        db.audit(_conn(request), user["tenant_id"], user["id"],
                 "medicine.image_updated", medicine["barcode"])
        return _image_panel(request, medicine, notice="Gambar ubat dikemas kini.")

    @app.post(
        "/medicines/{medicine_id}/image/remove",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def medicine_image_remove(request: Request, medicine_id: str):
        medicine = _medicine_from_path(request, medicine_id)
        if medicine is None:
            return ui.render_error(
                request, 404, "medicine_not_found", "Ubat tidak dijumpai.",
                title="Ubat tidak dijumpai",
            )
        removed = images.delete_image(
            request.app.state.settings, medicine["tenant_id"], medicine["id"]
        )
        user = _user(request)
        if removed:
            db.audit(_conn(request), user["tenant_id"], user["id"],
                     "medicine.image_removed", medicine["barcode"])
        return _image_panel(request, medicine, notice="Gambar dibuang.")

    # ------------------------------------------------------- medicine verification

    @app.post(
        "/medicines/{medicine_id}/verify",
        dependencies=[Depends(security.verify_csrf)],
    )
    def medicine_verify(request: Request, medicine_id: str):
        """Owner confirms the uses/dose text, so staff and scans may show it."""
        medicine = _medicine_from_path(request, medicine_id)
        if medicine is None:
            return ui.render_error(
                request, 404, "medicine_not_found", "Ubat tidak dijumpai.",
                title="Ubat tidak dijumpai",
            )
        user = _user(request)
        conn = _conn(request)
        db.verify_medicine(
            conn, user["tenant_id"], medicine["id"],
            source=f"Disahkan oleh {user['email']}",
        )
        db.audit(conn, user["tenant_id"], user["id"],
                 "medicine.verified", medicine["barcode"])
        return RedirectResponse(f"/medicines/{medicine['id']}", status_code=303)

    @app.post(
        "/catalog/images",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    async def catalog_images(request: Request, file: UploadFile | None = File(default=None)):
        user = _user(request)
        if file is None or not file.filename:
            return ui.render_error(
                request, 422, "invalid_images", "Pilih fail ZIP gambar terlebih dahulu.",
                title="Tiada fail",
            )
        payload = await file.read(images.MAX_ZIP_BYTES + 1)
        conn = _conn(request)
        try:
            report = images.import_zip(
                request.app.state.settings,
                user["tenant_id"],
                payload,
                lookup=lambda code: db.find_medicine_by_barcode(
                    conn, user["tenant_id"], code.upper()
                ),
            )
        except images.InvalidImage as exc:
            return ui.render_error(
                request, 422, "invalid_images", str(exc), title="ZIP tidak sah"
            )
        db.audit(conn, user["tenant_id"], user["id"], "catalog.images",
                 f"fail={re.sub(r'[^A-Za-z0-9._ -]', '_', str(file.filename))[:120]}; "
                 f"saved={report['saved']}; unmatched={len(report['unmatched'])}; "
                 f"skipped={len(report['skipped'])}")
        return ui.render(request, "partials/image_import_result.html", report=report)

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request):
        user = _user(request)
        scans = db.list_scans(_conn(request), user["tenant_id"], limit=100)
        return ui.render(request, "history.html", scans=scans)

    @app.get("/favourites", response_class=HTMLResponse)
    def favourites_page(request: Request):
        user = _user(request)
        items = db.list_favourites(_conn(request), user["tenant_id"], user["id"])
        return ui.render(request, "favourites.html", favourites=items)

    @app.post(
        "/favourites/{medicine_id}",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def favourite_add(request: Request, medicine_id: str):
        conn = _conn(request)
        user = _user(request)
        identifier = int(medicine_id) if medicine_id.isdigit() else 0
        medicine = db.get_medicine(conn, user["tenant_id"], identifier) if identifier else None
        if medicine is None:
            return ui.render_error(
                request, 404, "medicine_not_found", "Ubat tidak dijumpai.",
                title="Ubat tidak dijumpai",
            )
        db.add_favourite(conn, user["tenant_id"], user["id"], medicine["id"])
        return ui.render(request, "partials/favourite_button.html", medicine=medicine, favourite=True)

    @app.post(
        "/favourites/{medicine_id}/remove",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def favourite_remove(request: Request, medicine_id: str):
        conn = _conn(request)
        user = _user(request)
        identifier = int(medicine_id) if medicine_id.isdigit() else 0
        medicine = db.get_medicine(conn, user["tenant_id"], identifier) if identifier else None
        db.remove_favourite(conn, user["tenant_id"], user["id"], identifier)
        return ui.render(
            request, "partials/favourite_button.html", medicine=medicine, favourite=False
        )

    # --------------------------------------------------------- catalogue import

    @app.get("/catalog/import", response_class=HTMLResponse)
    def catalog_import_page(request: Request):
        return ui.render(
            request, "catalog_import.html", columns=catalog_import.TEMPLATE_COLUMNS
        )

    @app.get("/catalog/template.xlsx")
    def catalog_template(request: Request):
        return Response(
            catalog_import.template_workbook(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="catalog-code4care-template.xlsx"'
            },
        )

    @app.post(
        "/catalog/import",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    async def catalog_import_submit(
        request: Request,
        file: UploadFile | None = File(default=None),
        source: str = Form(default=""),
        verified: str = Form(default=""),
        dry_run: str = Form(default=""),
    ):
        conn = _conn(request)
        user = _user(request)
        if file is None or not file.filename:
            return ui.render(
                request, "catalog_import.html", status_code=422,
                error="Pilih fail katalog (.xlsx atau .csv) terlebih dahulu.",
            )

        payload = await file.read(catalog_import.MAX_BYTES + 1)
        safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", str(file.filename))[:120]
        try:
            preview = catalog_import.parse_upload(payload, safe_name)
        except catalog_import.ImportFormatError as exc:
            return ui.render(
                request, "catalog_import.html", status_code=422, error=str(exc)
            )

        mark_verified = verified.strip().lower() in TRUTHY_FORM_VALUES
        source_text = (source.strip() or "Import katalog")[:120]
        if dry_run.strip().lower() in TRUTHY_FORM_VALUES:
            return ui.render(
                request, "partials/import_result.html", preview=preview,
                counts=None, dry_run=True, file_name=safe_name,
            )

        counts = {"created": 0, "updated": 0, "unchanged": 0}
        try:
            for row in preview.rows:
                outcome = db.upsert_imported_medicine(
                    conn,
                    user["tenant_id"],
                    row.data,
                    verified=mark_verified or bool(row.data.get("__verified__")),
                    source=row.data.get("__source__") or source_text,
                )
                counts[outcome] += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        db.audit(
            conn, user["tenant_id"], user["id"], "catalog.import",
            (
                f"fail={safe_name}; created={counts['created']}; "
                f"updated={counts['updated']}; unchanged={counts['unchanged']}; "
                f"rejected={len(preview.problems)}"
            ),
        )
        return ui.render(
            request, "partials/import_result.html", preview=preview, counts=counts,
            dry_run=False, file_name=safe_name, mark_verified=mark_verified,
        )

    # ------------------------------------------------------------------- team pages

    @app.get("/team", response_class=HTMLResponse)
    def team_page(request: Request):
        users = db.list_users(_conn(request), _user(request)["tenant_id"])
        return ui.render(request, "team.html", users=users)

    @app.post(
        "/team/{user_id}/role",
        response_class=HTMLResponse,
        dependencies=[Depends(security.verify_csrf)],
    )
    def team_change_role(request: Request, user_id: str, role: str = Form(default="")):
        conn = _conn(request)
        actor = _user(request)
        if role not in permissions.ROLE_NAMES:
            return ui.render_error(
                request, 422, "invalid_role",
                "Peranan yang dipilih tidak sah. Pilih salah satu peranan dalam senarai.",
                title="Peranan tidak sah",
            )
        identifier = int(user_id) if user_id.isdigit() else 0
        target = db.get_user(conn, actor["tenant_id"], identifier) if identifier else None
        if target is None:
            return ui.render_error(
                request, 404, "user_not_found", "Ahli pasukan tidak dijumpai.",
                title="Tidak dijumpai",
            )
        if target["is_owner"] and role != permissions.ROLE_REGISTERED:
            return ui.render_error(
                request, 422, "invalid_role",
                "Pemilik perniagaan mesti kekal sebagai Registered user.",
                title="Peranan tidak sah",
            )
        db.set_user_role(conn, actor["tenant_id"], target["id"], role)
        db.audit(conn, actor["tenant_id"], actor["id"], "team.role_changed", f"{target['id']}:{role}")
        users = db.list_users(conn, actor["tenant_id"])
        return ui.render(request, "partials/team_table.html", users=users)

    # ------------------------------------------------------------ business pages

    @app.get("/billing", response_class=HTMLResponse)
    def billing(request: Request):
        tenant = db.get_tenant(_conn(request), _user(request)["tenant_id"])
        return ui.render(request, "billing.html", tenant=tenant)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        tenant = db.get_tenant(_conn(request), _user(request)["tenant_id"])
        return ui.render(request, "settings.html", tenant=tenant)

    @app.get("/usage", response_class=HTMLResponse)
    def usage(request: Request):
        user = _user(request)
        entries = db.list_audit(_conn(request), user["tenant_id"], limit=100)
        return ui.render(request, "usage.html", entries=entries)

    @app.get("/export/scans.csv")
    def export_scans(request: Request):
        user = _user(request)
        scans = db.list_scans(_conn(request), user["tenant_id"], limit=5000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["dijana_pada", "tarikh", "pengguna", "kod_bar", "nama_ubat", "sumber"])
        for scan in scans:
            writer.writerow([
                _csv_cell(db.utcnow()),
                _csv_cell(scan["created_at"]),
                _csv_cell(scan["user_id"]),
                _csv_cell(scan["barcode"]),
                _csv_cell(scan.get("medicine_name") or ""),
                _csv_cell(scan["source"]),
            ])
        db.audit(_conn(request), user["tenant_id"], user["id"], "export.scans", "csv")
        headers = {"Content-Disposition": 'attachment; filename="imbasan-code4care.csv"'}
        return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    return app


def __getattr__(name: str):
    """`uvicorn app.main:app` needs a module-level ASGI app.

    It is built on first access (PEP 562), so importing this module in tests or
    scripts never reads .env and never opens a database.
    """
    if name == "app":
        return create_app()
    raise AttributeError(name)
