"""M0 skeleton checks: the app starts, reads .env, and leaves the plan intact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_health_route_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_come_from_the_environment(settings):
    assert settings.database_path.endswith("code4care.db")
    assert settings.app_secret == "unit-test-secret-0123456789abcdef"
    assert settings.is_production is False


def test_env_file_is_ignored_by_git():
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines
    assert "data/" in lines


def test_blueprint_is_unchanged():
    digest = hashlib.sha256((ROOT / "blueprint.json").read_bytes()).hexdigest()
    recorded = (ROOT / "tests" / "blueprint.sha256").read_text().strip()
    assert digest == recorded, "blueprint.json must not be edited by the build agent"

    blueprint = json.loads((ROOT / "blueprint.json").read_text(encoding="utf-8"))
    assert blueprint["schema"] == "gigalab-blueprint/1"
    assert blueprint["status"] == "confirmed"
    assert [f["id"] for f in blueprint["requirements"]["features"]] == ["F1", "F2", "F3"]
    assert blueprint["stack"]["backend"]["value"] == "fastapi"
    assert blueprint["stack"]["database"]["value"] == "sqlite"


def test_static_assets_are_served_with_executable_types(client):
    """A .js served as text/plain is silently refused by browsers (htmx would not run)."""
    script = client.get("/static/vendor/htmx.min.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]

    stylesheet = client.get("/static/app.css")
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")

    icon = client.get("/static/favicon.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg")


def test_acceptance_tests_are_real_not_placeholders():
    folder = ROOT / "tests" / "acceptance"
    for name in (
        "test_f1_barcode_scanner.py",
        "test_f2_medicine_information_lookup.py",
        "test_f3_medicines_details_page.py",
    ):
        text = (folder / name).read_text(encoding="utf-8")
        assert "Not written yet" not in text
        assert "def test_ac" in text
