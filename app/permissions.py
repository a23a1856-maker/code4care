"""Roles, the permission matrix (docs/AUTH.md) and deny-by-default rules."""
from __future__ import annotations

PERM_SCAN = "f:barcode scanner"
PERM_LOOKUP = "f:Medicine Information Lookup"
PERM_DETAILS = "f:Medicines details page"
PERM_TEAM = "team"
PERM_BILLING = "billing"
PERM_SETTINGS = "settings"
PERM_USAGE = "usage"
PERM_EXPORT = "export"

ROLE_REGISTERED = "Registered user"
ROLE_PHARMACIST = "Pharmacist/health care professional"
ROLE_GUEST = "Guest User"
ROLE_ADMIN = "System Administrator"
ROLE_NAMES = (ROLE_REGISTERED, ROLE_PHARMACIST, ROLE_GUEST, ROLE_ADMIN)

ALL_PERMISSIONS = (
    PERM_SCAN,
    PERM_LOOKUP,
    PERM_DETAILS,
    PERM_TEAM,
    PERM_BILLING,
    PERM_SETTINGS,
    PERM_USAGE,
    PERM_EXPORT,
)

# Mirrors blueprint.json: core.authorization.matrix. A test asserts they match.
MATRIX: dict[str, frozenset[str]] = {
    ROLE_REGISTERED: frozenset(ALL_PERMISSIONS),
    ROLE_PHARMACIST: frozenset(),
    ROLE_GUEST: frozenset(),
    ROLE_ADMIN: frozenset(),
}

PERMISSION_LABELS = {
    PERM_SCAN: "barcode scanner",
    PERM_LOOKUP: "Medicine Information Lookup",
    PERM_DETAILS: "Medicines details page",
    PERM_TEAM: "Manage team and roles",
    PERM_BILLING: "Billing and plan",
    PERM_SETTINGS: "Business settings",
    PERM_USAGE: "Usage and logs",
    PERM_EXPORT: "Export data",
}

PUBLIC = "public"

NAV_ITEMS = (
    ("/scan", "Imbas & Cari", PERM_SCAN),
    ("/history", "Sejarah Imbasan", PERM_SCAN),
    ("/favourites", "Kegemaran", PERM_SCAN),
    ("/catalog/import", "Import Katalog", PERM_SETTINGS),
    ("/team", "Pasukan & Peranan", PERM_TEAM),
    ("/billing", "Langganan", PERM_BILLING),
    ("/settings", "Tetapan Perniagaan", PERM_SETTINGS),
    ("/usage", "Penggunaan & Log", PERM_USAGE),
    ("/export/scans.csv", "Eksport Data", PERM_EXPORT),
)


def allowed(role: str, permission: str) -> bool:
    """Deny by default: an unknown role, or an unknown permission, is refused."""
    if permission == PUBLIC:
        return True
    return permission in MATRIX.get(role, frozenset())


def needs_two_factor(role: str, is_owner: bool) -> bool:
    """Owners and administrators must pass a second factor (docs/AUTH.md)."""
    return bool(is_owner) or role == ROLE_ADMIN


def nav_for(role: str | None) -> list[dict]:
    if not role:
        return []
    return [
        {"path": path, "label": label}
        for path, label, permission in NAV_ITEMS
        if allowed(role, permission)
    ]


def permission_label(permission: str) -> str:
    return PERMISSION_LABELS.get(permission, permission)
