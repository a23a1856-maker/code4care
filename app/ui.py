"""Page rendering: one Jinja environment, one context shared by every page."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import permissions

ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _context(request: Request) -> dict:
    settings = request.app.state.settings
    user = getattr(request.state, "user", None)
    role = (user or {}).get("role")
    return {
        "request": request,
        "user": user,
        "role": role,
        "role_label": role or "",
        "nav": permissions.nav_for(role),
        "can_settings": permissions.allowed(role or "", permissions.PERM_SETTINGS),
        "current_path": request.url.path,
        "csrf_token": getattr(request.state, "csrf", ""),
        "tenant_name": getattr(request.state, "tenant_name", "") or "",
        "support_email": settings.support_email,
        "support_whatsapp": settings.support_whatsapp,
        "is_production": settings.is_production,
    }


def render(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    headers: dict | None = None,
    **context,
) -> HTMLResponse:
    payload = {**_context(request), **context}
    return templates.TemplateResponse(
        request, name, payload, status_code=status_code, headers=headers
    )


ERROR_TITLES = {
    "forbidden": "Tiada kebenaran",
    "email_unverified": "E-mel belum disahkan",
    "rate_limited": "Terlalu banyak permintaan",
    "locked": "Akaun dikunci sementara",
    "not_found": "Halaman tidak dijumpai",
    "medicine_not_found": "Ubat tidak dijumpai",
    "invalid_barcode": "Kod bar tidak sah",
    "invalid_lookup": "Carian tidak sah",
    "invalid_role": "Peranan tidak sah",
    "csrf": "Permintaan tidak sah",
    "server_error": "Masalah di pelayan",
}


def render_error(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    title: str | None = None,
) -> HTMLResponse:
    return render(
        request,
        "errors/error.html",
        status_code=status_code,
        error_code=code,
        error_message=message,
        error_title=title or ERROR_TITLES.get(code, "Ralat"),
    )
