"""Authorization: deny by default, the permission matrix, and role management."""
from __future__ import annotations

import pytest
from fastapi.responses import PlainTextResponse

from tests.conftest import sign_in
from tests.helpers import csrf_token

ALL_PERMISSION_ROUTES = [
    ("/scan", "f:barcode scanner"),
    ("/search", "f:Medicine Information Lookup"),
    ("/catalog/import", "settings"),
    ("/team", "team"),
    ("/billing", "billing"),
    ("/settings", "settings"),
    ("/usage", "usage"),
    ("/export/scans.csv", "export"),
]


def test_permission_matrix_matches_the_blueprint():
    import json
    from pathlib import Path

    from app.permissions import MATRIX, ROLE_NAMES

    blueprint = json.loads(
        (Path(__file__).resolve().parent.parent / "blueprint.json").read_text("utf-8")
    )
    blueprint_matrix = blueprint["core"]["authorization"]["matrix"]
    assert set(ROLE_NAMES) == set(blueprint_matrix)
    for role, permissions in blueprint_matrix.items():
        assert set(MATRIX[role]) == set(permissions), role
    assert blueprint["core"]["authorization"]["deny_by_default"] is True


def test_every_route_declares_a_rule(app):
    from fastapi.routing import APIRoute

    from app.main import ROUTE_RULES

    uncovered = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith("/static"):
            continue
        if route.path not in ROUTE_RULES:
            uncovered.append(route.path)
    assert uncovered == [], f"routes without a permission rule (deny by default): {uncovered}"


def test_a_route_with_no_permission_rule_is_refused(client, app):
    async def unruled():
        return PlainTextResponse("should never be reached")

    app.router.add_api_route("/__unruled", unruled, methods=["GET"])
    response = client.get("/__unruled")
    assert response.status_code == 403
    assert "should never be reached" not in response.text


def test_nobody_reaches_a_private_route_without_a_session(client):
    response = client.get("/export/scans.csv", follow_redirects=False)
    assert response.status_code == 303


@pytest.mark.parametrize("path,permission", ALL_PERMISSION_ROUTES)
@pytest.mark.parametrize(
    "role", ["pharmacist_a", "guest_a", "admin_a"]
)
def test_roles_without_a_permission_are_refused(client, world, role, path, permission):
    sign_in(client, world["users"][role]["email"])
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 403, (role, path)
    assert 'data-error="forbidden"' in response.text
    assert permission not in response.text


@pytest.mark.parametrize("path,permission", ALL_PERMISSION_ROUTES)
def test_registered_user_is_allowed(client, world, path, permission):
    sign_in(client, world["users"]["owner_a"]["email"])
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, (path, response.text[:200])
    assert 'data-error="forbidden"' not in response.text


def test_only_a_team_role_can_change_a_role(client, world):
    team_member = world["users"]["pharmacist_a"]

    sign_in(client, world["users"]["pharmacist_a"]["email"])
    denied_page = client.get("/team", follow_redirects=False)
    assert denied_page.status_code == 403
    denied = client.post(
        f"/team/{team_member['id']}/role",
        data={"role": "Registered user", "csrf_token": csrf_token(denied_page.text)},
        headers={"HX-Request": "true"},
    )
    assert denied.status_code == 403
    unchanged = world["conn"].execute(
        "SELECT role FROM users WHERE id = ?", (team_member["id"],)
    ).fetchone()["role"]
    assert unchanged == "Pharmacist/health care professional"

    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/team")
    assert page.status_code == 200
    allowed = client.post(
        f"/team/{team_member['id']}/role",
        data={"role": "Registered user", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert allowed.status_code == 200, allowed.text
    changed = world["conn"].execute(
        "SELECT role FROM users WHERE id = ?", (team_member["id"],)
    ).fetchone()["role"]
    assert changed == "Registered user"


def test_a_role_cannot_be_set_to_something_unknown(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/team")
    response = client.post(
        f"/team/{world['users']['pharmacist_a']['id']}/role",
        data={"role": "Superuser", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert 'data-error="invalid_role"' in response.text


def test_a_tenant_cannot_change_the_other_tenants_user(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/team")
    response = client.post(
        f"/team/{world['users']['owner_b']['id']}/role",
        data={"role": "Guest User", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 404
    role = world["conn"].execute(
        "SELECT role FROM users WHERE id = ?", (world["users"]["owner_b"]["id"],)
    ).fetchone()["role"]
    assert role == "Registered user"


def test_post_without_a_csrf_token_is_refused(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])
    response = client.post(
        f"/team/{world['users']['pharmacist_a']['id']}/role",
        data={"role": "Registered user"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 403
    assert 'data-error="csrf"' in response.text
