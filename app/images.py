"""Medicine images: validate, re-encode, store per tenant, and serve.

Uploads are untrusted. Every image is decoded by Pillow (which rejects anything
that is not really an image), rotated by its EXIF orientation, shrunk, and written
back as a plain JPEG — which also drops EXIF/GPS metadata and any embedded script.
Files live under the media directory, never inside the source tree.
"""
from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings

MAX_UPLOAD_BYTES = 5 * 1024 * 1024          # one image
MAX_ZIP_BYTES = 25 * 1024 * 1024            # one bulk archive
MAX_ZIP_ENTRIES = 300
MAX_ENTRY_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1200
JPEG_QUALITY = 82
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
Image.MAX_IMAGE_PIXELS = 40_000_000


class InvalidImage(ValueError):
    """The file is not a usable image; the caller shows this message."""


def target_path(settings: Settings, tenant_id: int, medicine_id: int) -> Path:
    return Path(settings.media_dir) / str(tenant_id) / f"{medicine_id}.jpg"


def process_image(data: bytes) -> bytes:
    if not data:
        raise InvalidImage("Fail gambar kosong.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImage("Gambar terlalu besar (maksimum 5 MB).")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImage(
            "Fail ini bukan gambar yang sah. Guna JPG, PNG atau WebP."
        ) from exc
    except Image.DecompressionBombError as exc:  # pragma: no cover - defensive
        raise InvalidImage("Gambar terlalu besar untuk diproses.") from exc

    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def save_image(settings: Settings, tenant_id: int, medicine_id: int, data: bytes) -> Path:
    processed = process_image(data)
    path = target_path(settings, tenant_id, medicine_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(processed)
    temporary.replace(path)
    return path


def delete_image(settings: Settings, tenant_id: int, medicine_id: int) -> bool:
    path = target_path(settings, tenant_id, medicine_id)
    if path.exists():
        path.unlink()
        return True
    return False


def has_image(settings: Settings, tenant_id: int, medicine_id: int) -> bool:
    return target_path(settings, tenant_id, medicine_id).is_file()


def image_version(settings: Settings, tenant_id: int, medicine_id: int) -> int:
    """Cache-buster for the <img> URL, so a replaced photo shows at once."""
    path = target_path(settings, tenant_id, medicine_id)
    return int(path.stat().st_mtime) if path.is_file() else 0


def read_image(settings: Settings, tenant_id: int, medicine_id: int) -> bytes | None:
    path = target_path(settings, tenant_id, medicine_id)
    if not path.is_file():
        return None
    return path.read_bytes()


def medicine_id_from_name(filename: str) -> str:
    """The catalogue code is the file name without its extension."""
    return PurePosixPath(filename.replace("\\", "/")).stem.strip()


def import_zip(settings: Settings, tenant_id: int, data: bytes, lookup) -> dict:
    """Attach images from a ZIP whose file names are catalogue codes.

    `lookup(code)` returns a medicine dict or None, so the caller keeps every
    database query tenant scoped.
    """
    if not data:
        raise InvalidImage("Fail ZIP kosong.")
    if len(data) > MAX_ZIP_BYTES:
        raise InvalidImage("ZIP terlalu besar (maksimum 25 MB).")
    try:
        archive = ZipFile(io.BytesIO(data))
    except BadZipFile as exc:
        raise InvalidImage("Fail ini bukan ZIP yang sah.") from exc

    saved, unmatched, skipped = 0, [], []
    with archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if len(entries) > MAX_ZIP_ENTRIES:
            raise InvalidImage(f"ZIP mempunyai terlalu banyak fail (maksimum {MAX_ZIP_ENTRIES}).")
        for info in entries:
            suffix = PurePosixPath(info.filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                skipped.append(info.filename)
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                skipped.append(info.filename)
                continue
            medicine = lookup(medicine_id_from_name(info.filename))
            if medicine is None:
                unmatched.append(info.filename)
                continue
            try:
                save_image(settings, tenant_id, medicine["id"], archive.read(info))
            except InvalidImage:
                skipped.append(info.filename)
                continue
            saved += 1

    return {
        "saved": saved,
        "unmatched": unmatched,
        "skipped": skipped,
        "total": len(entries),
    }
