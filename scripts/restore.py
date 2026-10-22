"""Restore a CODE4CARE database from a backup, and prove it is readable.

    python -m scripts.restore --backup backups/code4care-20261022T030000Z.db \
        --target /tmp/restored.db

Medicine pictures are stored outside the database; pass the matching archive to
restore them too:

    python -m scripts.restore --backup backups/code4care-...db \
        --media-zip backups/code4care-...db.media.zip \
        --media-target data/medicine-images

Restore to a new path first when you are practising; only restore over the live
file while the app is stopped.
"""
from __future__ import annotations

import argparse
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED_TABLES = ("tenants", "users", "medicines", "scans", "audit_log")


def restore_database(backup: str | Path, target: str | Path) -> Path:
    backup = Path(backup)
    target = Path(target)
    if not backup.is_file():
        raise FileNotFoundError(f"backup not found: {backup}")
    target.parent.mkdir(parents=True, exist_ok=True)

    backup_conn = sqlite3.connect(str(backup))
    target_conn = sqlite3.connect(str(target))
    try:
        with target_conn:
            backup_conn.backup(target_conn)
    finally:
        target_conn.close()
        backup_conn.close()

    check = sqlite3.connect(str(target))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        present = {
            row[0]
            for row in check.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        check.close()

    if integrity != "ok":
        raise RuntimeError(f"restored database failed its integrity check: {integrity}")
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise RuntimeError(f"restored database is missing tables: {missing}")
    return target


def restore_media(media_zip: str | Path, target_dir: str | Path) -> Path:
    """Extract a media backup, refusing entries that try to escape the folder."""
    media_zip = Path(media_zip)
    target = Path(target_dir)
    if not media_zip.is_file():
        raise FileNotFoundError(f"media backup not found: {media_zip}")
    target.mkdir(parents=True, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(media_zip) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise RuntimeError(f"unsafe path in media backup: {info.filename}")
            destination = target.joinpath(*name.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
            restored += 1
    if restored == 0:
        raise RuntimeError("media backup held no files")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore the CODE4CARE SQLite database")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--target", default="data/code4care.db")
    parser.add_argument("--media-zip", default="", help="archive of medicine pictures")
    parser.add_argument("--media-target", default="data/medicine-images")
    args = parser.parse_args(argv)

    restored = restore_database(args.backup, args.target)
    print(f"database restored and checked: {restored}")
    if args.media_zip:
        media = restore_media(args.media_zip, args.media_target)
        print(f"medicine pictures restored: {media}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
