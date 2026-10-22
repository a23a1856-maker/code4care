# Medicine pictures

Added at the owner's request after version 1. `blueprint.json` is unchanged.

## Where pictures appear

- the medicine details page (`/medicines/<id>`): a photo card beside the details,
  with a neutral "Tiada gambar" placeholder when there is none
- search results on **Imbas & Cari** (`/scan`, and `/search`): a small thumbnail
- scan results (`/scan`): the photo beside the found medicine

## How to add a picture

**One medicine:** open its details page and use "Muat naik gambar" under the photo
card (visible to a role with the `settings` permission). "Buang gambar" removes it.

**A whole catalogue:** on `/catalog/import`, use "Import gambar (ZIP)". Name every
file with the product code — the file name (without extension) must equal the
barcode, and subfolders are fine:

```
gambar.zip
├── img/C4C-0003.jpg          -> matches barcode C4C-0003
├── 9550010000015.jpg         -> matches barcode 9550010000015
└── 9550010000016.png         -> PNG is accepted, stored as JPEG
```

Files that match nothing, or are not usable images, are listed in the result.

## Rules and limits

| Rule | Value |
|---|---|
| Formats | JPG, PNG, WebP (decoded by Pillow, so a renamed `.txt` is refused) |
| One upload | 5 MB maximum |
| ZIP upload | 25 MB, 300 files, 5 MB per file |
| Stored size | longest side 1200 px, JPEG quality 82 |
| Metadata | stripped: EXIF, GPS and embedded profiles are dropped by re-encoding |
| Storage | `MEDIA_PATH` (default `data/medicine-images/<tenant_id>/<medicine_id>.jpg`) |
| Serving | `GET /medicines/<id>/image`, tenant scoped, `Cache-Control: private` |
| Permissions | view: `f:Medicines details page`; upload/remove: `settings` |

A medicine id from another business returns 404 on both the page and the image, and
files are written under the tenant folder, so no picture can leak across tenants.
Uploading is CSRF protected and recorded in the usage log
(`medicine.image_updated`, `medicine.image_removed`, `catalog.images`).

The image route is behind the same permission as the details page, and the CSP
already allows `img-src 'self'`, so no third-party image host is involved.

## Backups

Pictures are files, not rows, so the normal database backup would miss them:

```bash
python -m scripts.backup --source data/code4care.db \
    --destination backups/ --media data/medicine-images

python -m scripts.restore --backup backups/code4care-....db \
    --media-zip backups/code4care-....db.media.zip \
    --media-target data/medicine-images
```

The restore refuses archive entries that try to escape the target folder (zip slip).

## Tests

`tests/test_medicine_images.py` covers upload and display, re-encoding, metadata
stripping, bad and oversize files, CSRF, removal, permissions per role, tenant
isolation on disk and over HTTP, the ZIP import (matched / unmatched / skipped),
search and scan thumbnails, and the media backup-and-restore round trip.

## The demo photo pack (`code4care-photos.zip`)

The photos supplied with the catalogue are named by product code — `C4C-0001.jpg`
through `C4C-0039.jpg` — which is exactly the lookup rule: the file name (without
extension) must equal the medicine's barcode. Uploaded through **Import Katalog →
Fail ZIP gambar**, the pack produced **39 saved, 0 unmatched, 0 skipped**.

Storage after the import: `data/medicine-images/1/17.jpg` … `55.jpg`, one file per
medicine, matched to the imported catalogue rows (ids 17–55). Each file was decoded
by Pillow, turned upright, resized to 1200 px, re-encoded as JPEG and stripped of
metadata before being written, so the pack's contents cannot carry GPS or EXIF into
the app.

A spot check against the catalogue confirms the pairing: C4C-0010 → Piriton 4 mg,
C4C-0025 → Norvasc 5 mg, C4C-0039 → Ferrous Fumarate 200 mg.

Note that a picture does not change whether a medicine is **verified**: the imported
rows still hide uses and dose until the owner presses “Sahkan maklumat ubat” on each
medicine they have checked.
