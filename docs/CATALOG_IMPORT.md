# Catalogue import (Excel / CSV)

Added at the owner's request after version 1. `blueprint.json` is unchanged: this
is an extra module on top of F1–F3, not a change to a requirement. It lives under
the existing "Business settings" permission, so no role gains a new permission.

## Where

- Page: `/catalog/import`, also in the navigation as **Import Katalog**
- Template: `/catalog/template.xlsx`
- Permission: `settings` — Registered user yes; Pharmacist, Guest User and System
  Administrator refused (verified by `tests/test_authorization.py` and
  `tests/test_catalog_import.py`)

## Accepted files

| Rule | Value |
|---|---|
| Formats | `.xlsx` (Excel 2007+) and `.csv` (UTF-8, UTF-8 with BOM, or CP1252) |
| Refused | `.xls`, `.xlsm` (macros), anything else |
| Size | 5 MB maximum |
| Rows | 2 000 data rows per import |
| Sheet | the active sheet; the first row must be the header |
| Cell length | 2 000 characters per cell; control characters and formulas are refused |

A file that breaks a whole-file rule is refused with a clear message and nothing
is written. A row that breaks a row rule is listed in the report with its row
number; the other rows are imported in one transaction.

## Columns

Column order does not matter. Only `barcode` and `name` are required.
`catalog code4care.csv` (and its `.xlsx` twin in the project root) shows the
supplier layout this module was built around.

| Column | Required | Meaning |
|---|---|---|
| `barcode` | yes | EAN-8 / UPC-A / EAN-13 (8, 12 or 13 digits, check digit verified) or an internal code such as `C4C-0001` |
| `name` | yes | medicine name as printed on the pack |
| `brand`, `generic`, `strength`, `form`, `manufacturer` | no | brand, active ingredient, strength, dosage form, manufacturer |
| `condition` / `category` | no | e.g. "Demam & Sakit" |
| `uses`, `dosage`, `warnings`, `sideEffects`, `storage` | no | the medical text shown on the details page |
| `howToTake`, `pack`, `price`, `stock`, `expiry`, `notes`, `image` | no | catalogue metadata, shown under "Maklumat katalog" |
| `regClass`, `regNo`, `holder`, `origin`, `halal` | no | registration metadata |
| `verified`, `source` | no | per-row verification flag and its source |
| `source` | no | recorded only when the row is imported as verified |

Malay aliases are accepted too (`nama`, `jenama`, `kegunaan`, `amaran`,
`kesan sampingan`, `penyimpanan`, `harga`, `stok`, `tarikh luput`, `nota`).
Unknown columns are ignored and listed in the result.

### Scanning vs searching internal codes

A camera reads EAN/UPC digits only, so an internal code such as `C4C-0001`
cannot be scanned. It can still be found with **Imbas & Cari**.

## Verified rows

Imported rows are **unverified by default**: the details page shows the name,
brand, ingredient, strength, form, manufacturer and catalogue metadata, but not
the dosage or warnings. That matches F3 ("when verified information is available").

Tick **"Tandakan baris yang diimport sebagai disahkan"** to import them as verified
(and record a source). Do that only after an owner or pharmacist has checked the
list against the product labels. Re-importing without the flag never downgrades a
row that is already verified.

## Repeat imports

Rows are matched on `(tenant_id, barcode)`:

- new barcode → added
- existing barcode with changed text → updated
- identical text → unchanged (not rewritten)
- the same barcode twice in one file → the second row is rejected

So a supplier sends a corrected file every month and you can re-upload it safely.

## Safety

- The file is untrusted input: parsed in memory, size and row capped, and every
  cell is validated before any SQL runs.
- Formulas (`=...`) are refused rather than evaluated; `.xlsm` is refused.
- Imported text is escaped by the templates (no HTML injection).
- The scan CSV export prefixes `= + - @` with an apostrophe, so a catalogue value
  cannot become a formula in Excel.
- Every import is written to the usage log: file name, created/updated/unchanged
  and rejected counts, tenant scoped.

## Tests

`tests/test_catalog_import.py` covers the page, permissions, xlsx and CSV uploads,
per-tenant isolation, upsert without duplicates, row-level rejections with line
numbers, dry run, verified/unverified display, bad files, oversize uploads, the
template download, CSRF, the usage log and CSV-injection neutralisation.

## After importing: verify before the dose shows

Imports are written **unverified** on purpose — a spreadsheet is not a checked
label. An unverified medicine still appears in search, shows its name, brand,
strength, form, pack and barcode, and is saved in scan history, but its uses, dose,
how-to-take and warnings stay hidden on both the details page and the scan result.

To unlock them, the owner opens the medicine and presses **“Sahkan maklumat ubat”**
(`POST /medicines/{id}/verify`, `settings` permission, tenant scoped). That stamps
`verified = 1`, the verifier's e-mail in `source`, the date in `verified_at`, and an
`medicine.verified` line in the usage log.

`tests/test_scan_details.py` covers the unlocked card, the QR payload path, the
hidden state before verification, owner-only access and cross-tenant refusal.
