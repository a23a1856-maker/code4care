# Test labels (barcode + QR) for trying the scanner

Built so a pharmacy can exercise the scanner without a physical box of medicine.
Open `/labels/test` (navigation is not needed; the link is on the scan page) and
you get a printable card per medicine in your catalogue:

- the barcode: **EAN-13** when the product code is a real EAN, otherwise
  **Code 128** for internal codes such as `C4C-0001`
- a **QR code** whose whole content is that same product code
- the name, strength, form and the printed digits

Print the page (two cards per row, header and footer hidden) or open it on a
second screen and point the phone at it.

## Which labels the scanner accepts

| Label | Camera result |
|---|---|
| EAN-13 / EAN-8 / UPC-A | decoded and looked up |
| Code 128 (internal code) | decoded; looked up **only if** that code exists in your catalogue |
| QR with the product code | decoded (the detector includes `qr_code`), looked up like any code |
| QR with a URL or other text | refused: "Kod bar tidak sah" |

An internal code or QR only succeeds when the catalogue really contains it, so a
random QR code cannot create noise in the scan history.

## Route and permissions

- `/labels/test` requires the `f:barcode scanner` permission, like `/scan`.
- Pharmacist, Guest User and System Administrator are refused (403); signed-out
  visitors are redirected to sign in.
- 24 cards per page; `?page=2` for the rest.

## How it is built

- `app/labels.py`: `barcode_svg()` (python-barcode) and `qr_svg()` (segno).
- QR specifics: a **standard QR** (`micro=False`) with error correction H, a
  3-module quiet zone, shown at 140 px. Micro QR is deliberately avoided: it is
  smaller, but many phone scanners (including Chrome's `BarcodeDetector`) cannot
  read it. Verified by decoding the rendered page with zxing-cpp: the QR returns
  the product code, and so does the EAN-13 beside it.
- The generator output is normalised for the web: millimetres converted to CSS
  pixels with a `viewBox`, and inline `style="fill:..."` turned into `fill`
  attributes — our CSP forbids inline styles, and without that every bar (and the
  white background) painted black.
- `templates/test_labels.html` and the `.label-*` rules in `static/app.css`,
  including a print stylesheet.
- Tests: `tests/test_labels.py` (generators, page, pagination, permissions,
  scanning internal codes and QR-equivalent values, unknown codes refused).
