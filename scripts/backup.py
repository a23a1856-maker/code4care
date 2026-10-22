"""Daily SQLite backup, using the database's own online backup API.

Run from cron (or a systemd timer) on the VPS:

    python -m scripts.backup --source data/code4care.db --destination backups/

Medicine pictures live outside the database, so pass `--media data/medicine-images`
to archive them beside it. A backup is only a backup once it has been restored:
see scripts/restore.py and docs/OPERATIONS.md.
"""
from __future__ import annotations

import argparse
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def backup_database(source: str | Path, destination: str | Path) -> Path:
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    source_conn = sqlite3.connect(str(source))
    destination_conn = sqlite3.connect(str(destination))
    try:
        with destination_conn:
            source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()

    check = sqlite3.connect(str(destination))
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        raise RuntimeError(f"backup failed its integrity check: {result}")
    return destination


def backup_media(media_dir: str | Path, destination: str | Path) -> Path:
    """Zip the uploaded medicine pictures (they are not inside the database)."""
    media_dir = Path(media_dir)
    destination = Path(destination)
    if not media_dir.is_dir():
        raise FileNotFoundError(f"media directory not found: {media_dir}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(media_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(media_dir).as_posix())
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up the CODE4CARE SQLite database")
    parser.add_argument("--source", default="data/code4care.db")
    parser.add_argument("--destination", default="")
    parser.add_argument("--media", default="", help="folder of medicine pictures to zip")
    args = parser.parse_args(argv)

    destination = args.destination
    if not destination:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = f"backups/code4care-{stamp}.db"
    elif destination.endswith(("/", "\\")):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = f"{destination.rstrip('/')}/code4care-{stamp}.db"

    written = backup_database(args.source, destination)
    print(f"backup written: {written}")
    if args.media:
        media_zip = backup_media(args.media, str(written) + ".media.zip")
        print(f"media backup written: {media_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
