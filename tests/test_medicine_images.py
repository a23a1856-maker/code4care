"""Medicine pictures: upload, storage, serving, tenant isolation and bulk ZIP."""
from __future__ import annotations

import io
import zipfile

import pytest
from PIL import Image

from app.seed_data import ean13
from tests.conftest import sign_in
from tests.helpers import csrf_token

DESCRIPTION = "RAHSIA-123"


def jpeg_bytes(size=(640, 480), description: str | None = None) -> bytes:
    image = Image.new("RGB", size, (190, 40, 40))
    exif = Image.Exif()
    if description:
        exif[0x010E] = description  # ImageDescription
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def png_bytes(size=(300, 200)) -> bytes:
    image = Image.new("RGB", size, (30, 120, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def upload(client, signed, medicine_id: int, payload: bytes, filename="ubat.jpg"):
    return client.post(
        f"/medicines/{medicine_id}/image/upload",
        data={"csrf_token": signed.csrf},
        files={"image": (filename, payload, "image/jpeg")},
        headers={"HX-Request": "true"},
    )


def test_upload_shows_the_picture_and_serves_it(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    page = client.get(f"/medicines/{medicine['id']}")
    assert 'data-image="missing"' in page.text
    assert "Tiada gambar" in page.text

    response = upload(client, signed, medicine["id"], jpeg_bytes(description=DESCRIPTION))
    assert response.status_code == 200, response.text
    assert 'data-image="present"' in response.text
    assert 'class="medicine-photo"' in response.text

    served = client.get(f"/medicines/{medicine['id']}/image")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.content[:2] == b"\xff\xd8"
    assert served.headers["cache-control"].startswith("private")

    page = client.get(f"/medicines/{medicine['id']}")
    assert f'/medicines/{medicine["id"]}/image' in page.text

    actions = client.get("/usage")
    assert "medicine.image_updated" in actions.text


def test_upload_reencodes_and_strips_metadata(client, world):
    medicine = world["medicines"]["a"][1]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, signed, medicine["id"], jpeg_bytes(description=DESCRIPTION))

    settings = client.app.state.settings
    stored = (settings.media_dir / str(world["tenants"]["a"]) / f"{medicine['id']}.jpg").read_bytes()
    assert stored[:2] == b"\xff\xd8", "always saved as JPEG"
    assert DESCRIPTION.encode() not in stored, "EXIF must not survive the upload"

    # A PNG is accepted too, and still stored as JPEG.
    png_medicine = world["medicines"]["a"][2]
    response = upload(client, signed, png_medicine["id"], png_bytes(), "ubat.png")
    assert response.status_code == 200
    png_stored = (settings.media_dir / str(world["tenants"]["a"]) / f"{png_medicine['id']}.jpg")
    assert png_stored.read_bytes()[:2] == b"\xff\xd8"


def test_bad_files_are_refused(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    settings = client.app.state.settings
    target = settings.media_dir / str(world["tenants"]["a"]) / f"{medicine['id']}.jpg"

    not_an_image = upload(client, signed, medicine["id"], b"<html>hello</html>", "x.jpg")
    assert not_an_image.status_code == 422
    assert "bukan gambar" in not_an_image.text
    assert not target.exists()

    too_big = upload(client, signed, medicine["id"], b"x" * (5 * 1024 * 1024 + 10), "big.jpg")
    assert too_big.status_code == 422
    assert "terlalu besar" in too_big.text

    missing = client.post(
        f"/medicines/{medicine['id']}/image/upload",
        data={"csrf_token": signed.csrf},
        files={},
        headers={"HX-Request": "true"},
    )
    assert missing.status_code == 422

    no_csrf = client.post(
        f"/medicines/{medicine['id']}/image/upload",
        files={"image": ("a.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert no_csrf.status_code == 403
    assert not target.exists()


def test_image_can_be_removed(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, signed, medicine["id"], jpeg_bytes())
    assert client.get(f"/medicines/{medicine['id']}/image").status_code == 200

    removed = client.post(
        f"/medicines/{medicine['id']}/image/remove",
        data={"csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert removed.status_code == 200
    assert 'data-image="missing"' in removed.text
    assert client.get(f"/medicines/{medicine['id']}/image").status_code == 404
    assert "medicine.image_removed" in client.get("/usage").text


def test_other_business_cannot_see_or_set_the_picture(client, world):
    a_medicine = world["medicines"]["a"][0]
    owner_a = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, owner_a, a_medicine["id"], jpeg_bytes())

    owner_b = sign_in(client, world["users"]["owner_b"]["email"])
    assert client.get(f"/medicines/{a_medicine['id']}/image").status_code == 404
    assert client.get(f"/medicines/{a_medicine['id']}").status_code == 404
    assert upload(client, owner_b, a_medicine["id"], jpeg_bytes()).status_code == 404

    settings = client.app.state.settings
    leaked = settings.media_dir / str(world["tenants"]["b"]) / f"{a_medicine['id']}.jpg"
    assert not leaked.exists()


@pytest.mark.parametrize("role", ["pharmacist_a", "guest_a", "admin_a"])
def test_other_roles_cannot_touch_pictures(client, world, role):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"][role]["email"])

    assert client.get(f"/medicines/{medicine['id']}/image", follow_redirects=False).status_code == 403
    posted = upload(client, signed, medicine["id"], jpeg_bytes())
    assert posted.status_code == 403


def test_zip_import_matches_files_by_barcode(client, world):
    tenant_a = world["tenants"]["a"]
    ean_code = world["medicines"]["a"][0]["barcode"]
    world["conn"].execute(
        "INSERT INTO medicines (tenant_id, barcode, name, created_at, updated_at) "
        "VALUES (?, 'C4C-0301', 'Ubat ZIP', '2026-10-22T00:00:00+00:00', '2026-10-22T00:00:00+00:00')",
        (tenant_a,),
    )
    world["conn"].commit()

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("img/" + ean_code + ".jpg", jpeg_bytes())
        archive.writestr("C4C-0301.jpg", png_bytes())
        archive.writestr("1111111111111.jpg", jpeg_bytes())
        archive.writestr("nota.txt", b"hello")

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    response = client.post(
        "/catalog/images",
        data={"csrf_token": signed.csrf},
        files={"file": ("gambar.zip", archive_bytes.getvalue(), "application/zip")},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200, response.text
    assert 'data-image-import="done"' in response.text
    assert "<strong>2</strong> gambar disimpan" in response.text
    assert "1111111111111.jpg" in response.text
    assert "nota.txt" in response.text

    settings = client.app.state.settings
    ean_id = world["medicines"]["a"][0]["id"]
    internal_id = world["conn"].execute(
        "SELECT id FROM medicines WHERE tenant_id = ? AND barcode = 'C4C-0301'", (tenant_a,)
    ).fetchone()["id"]
    assert (settings.media_dir / str(tenant_a) / f"{ean_id}.jpg").is_file()
    assert (settings.media_dir / str(tenant_a) / f"{internal_id}.jpg").is_file()
    assert client.get(f"/medicines/{ean_id}/image").status_code == 200
    assert "catalog.images" in client.get("/usage").text


def test_zip_that_is_not_a_zip_is_refused(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    response = client.post(
        "/catalog/images",
        data={"csrf_token": signed.csrf},
        files={"file": ("gambar.zip", b"not a zip", "application/zip")},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert "bukan ZIP" in response.text


def test_search_and_scan_show_the_picture(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, signed, medicine["id"], jpeg_bytes())

    search_page = client.get("/search")
    found = client.post(
        "/search",
        data={"q": medicine["barcode"], "csrf_token": csrf_token(search_page.text)},
        headers={"HX-Request": "true"},
    )
    assert found.status_code == 200
    assert 'class="thumb"' in found.text

    scan_page = client.get("/scan")
    scanned = client.post(
        "/scan/lookup",
        data={"barcode": medicine["barcode"], "csrf_token": csrf_token(scan_page.text)},
        headers={"HX-Request": "true"},
    )
    assert scanned.status_code == 200
    assert 'class="scan-photo"' in scanned.text


def test_media_backup_and_restore_round_trip(client, world, tmp_path):
    """Pictures live outside the database, so they need their own backup."""
    from scripts.backup import backup_media
    from scripts.restore import restore_media

    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, signed, medicine["id"], jpeg_bytes())

    settings = client.app.state.settings
    stored = settings.media_dir / str(world["tenants"]["a"]) / f"{medicine['id']}.jpg"
    assert stored.is_file()

    archive = backup_media(settings.media_dir, tmp_path / "media.zip")
    assert archive.is_file()
    stored.unlink()
    assert not stored.exists()

    restore_media(archive, settings.media_dir)
    assert stored.is_file()
    assert client.get(f"/medicines/{medicine['id']}/image").status_code == 200


def test_media_restore_refuses_a_path_traversal_archive(tmp_path):
    import zipfile

    from scripts.restore import restore_media

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../escaped.jpg", b"x")
    with pytest.raises(RuntimeError):
        restore_media(evil, tmp_path / "media")
    assert not (tmp_path / "escaped.jpg").exists()


def test_picture_is_tenant_scoped_on_disk(client, world):
    settings = client.app.state.settings
    tenant_a = world["tenants"]["a"]
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    upload(client, signed, medicine["id"], jpeg_bytes())

    stored = settings.media_dir / str(tenant_a) / f"{medicine['id']}.jpg"
    assert stored.is_file()
    others = [p for p in settings.media_dir.rglob("*.jpg") if p != stored]
    assert others == []
