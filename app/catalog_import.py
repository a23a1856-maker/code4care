"""Import a pharmacy catalogue from Excel (.xlsx) or CSV.

Uploaded files are untrusted: this module reads them in memory, caps the size and
row count, validates every cell, refuses formulas, and turns each row into the
fields `app.db.upsert_imported_medicine` expects. Nothing here touches the
database, so a bad file can never leave a half-saved catalogue.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook

from app.barcode import InvalidBarcode, validate_barcode

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
MAX_TEXT = 2000
MAX_BARCODE = 32
SKU_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRUE_VALUES = {"1", "ya", "yes", "true", "y", "t"}

# Header text (normalised) -> field used by the database.
ALIASES = {
    "barcode": "barcode",
    "kodbar": "barcode",
    "productcode": "barcode",
    "sku": "barcode",
    "code": "barcode",
    "name": "name",
    "productname": "name",
    "nama": "name",
    "product": "name",
    "brand": "brand",
    "jenama": "brand",
    "generic": "active_ingredient",
    "genericname": "active_ingredient",
    "activeingredient": "active_ingredient",
    "bahanaktif": "active_ingredient",
    "strength": "strength",
    "kekuatan": "strength",
    "form": "dosage_form",
    "dosageform": "dosage_form",
    "bentukdos": "dosage_form",
    "manufacturer": "manufacturer",
    "maker": "manufacturer",
    "pengeluar": "manufacturer",
    "uses": "uses",
    "indications": "uses",
    "kegunaan": "uses",
    "dosage": "dosage_instructions",
    "dose": "dosage_instructions",
    "dos": "dosage_instructions",
    "dosageinstructions": "dosage_instructions",
    "warnings": "warnings",
    "warning": "warnings",
    "amaran": "warnings",
    "sideeffects": "side_effects",
    "sideeffect": "side_effects",
    "kesansampingan": "side_effects",
    "storage": "storage",
    "penyimpanan": "storage",
    "category": "category",
    "condition": "category",
    "kategori": "category",
    "howtotake": "how_to_take",
    "administration": "how_to_take",
    "carapengambilan": "how_to_take",
    "regclass": "reg_class",
    "kelas": "reg_class",
    "regno": "reg_no",
    "registrationno": "reg_no",
    "holder": "holder",
    "pemegang": "holder",
    "origin": "origin",
    "negaraasal": "origin",
    "pack": "pack_size",
    "packsize": "pack_size",
    "pembungkusan": "pack_size",
    "halal": "halal",
    "price": "price",
    "harga": "price",
    "stock": "stock",
    "stok": "stock",
    "expiry": "expiry",
    "tarikhluput": "expiry",
    "notes": "notes",
    "nota": "notes",
    "image": "image",
    "gambar": "image",
    "verified": "verified",
    "disahkan": "verified",
    "source": "source",
    "sumber": "source",
}

CORE_FIELDS = (
    "name",
    "brand",
    "active_ingredient",
    "strength",
    "dosage_form",
    "manufacturer",
    "uses",
    "dosage_instructions",
    "warnings",
    "side_effects",
    "storage",
    "category",
)
EXTRA_FIELDS = (
    "how_to_take",
    "reg_class",
    "reg_no",
    "holder",
    "origin",
    "pack_size",
    "halal",
    "price",
    "stock",
    "expiry",
    "notes",
    "image",
)

# The columns the template offers, in the order they appear in the file.
TEMPLATE_COLUMNS = (
    ("barcode", True, "Kod bar EAN-8/12/13, atau kod dalaman seperti C4C-0001"),
    ("name", True, "Nama ubat seperti pada bungkusan"),
    ("brand", False, "Jenama dagang"),
    ("generic", False, "Bahan aktif"),
    ("strength", False, "Kekuatan, contoh 500 mg"),
    ("form", False, "Bentuk dos, contoh Tablet, Sirap"),
    ("manufacturer", False, "Pengeluar atau pemegang pendaftaran"),
    ("condition", False, "Kategori, contoh Demam & Sakit"),
    ("uses", False, "Kegunaan"),
    ("dosage", False, "Dos yang disyorkan"),
    ("howToTake", False, "Cara pengambilan"),
    ("warnings", False, "Amaran keselamatan"),
    ("sideEffects", False, "Kesan sampingan"),
    ("storage", False, "Cara penyimpanan"),
    ("pack", False, "Pembungkusan"),
    ("price", False, "Harga (RM)"),
    ("stock", False, "Bilangan stok"),
    ("expiry", False, "Tarikh luput, contoh 2027-06"),
    ("notes", False, "Nota dalaman"),
)


class ImportFormatError(ValueError):
    """The file as a whole cannot be used; nothing is imported."""


@dataclass
class ParsedRow:
    line: int
    data: dict


@dataclass
class RowProblem:
    line: int
    message: str


@dataclass
class ImportPreview:
    rows: list[ParsedRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    total_rows: int = 0
    skipped_empty: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    file_kind: str = ""
    sheet_name: str = ""


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).strip().lower())


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "ya" if value else "tidak"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value).strip()


def _clean_text(value, label: str, line: int) -> str:
    text = _cell_text(value)
    if not text:
        return ""
    if text.startswith("="):
        raise ValueError(f"{label}: formula tidak dibenarkan. Masukkan nilai biasa.")
    if CONTROL_PATTERN.search(text):
        raise ValueError(f"{label}: mengandungi aksara kawalan yang tidak sah.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"{label}: terlalu panjang (maksimum {MAX_TEXT} aksara).")
    return text


def normalise_product_code(raw) -> str:
    """EAN/UPC for scanning, or an internal catalogue code such as C4C-0001."""
    text = _cell_text(raw)
    if not text:
        raise ValueError("Kod bar tiada.")
    if len(text) > MAX_BARCODE:
        raise ValueError("Kod bar terlalu panjang (maksimum 32 aksara).")
    if text.isdigit():
        try:
            return validate_barcode(text)
        except InvalidBarcode as exc:
            raise ValueError(str(exc).replace("Kod bar tidak sah. ", "")) from exc
    if not SKU_PATTERN.match(text) or not any(ch.isdigit() for ch in text):
        raise ValueError(
            "Kod bar mesti EAN/UPC (8, 12 atau 13 digit) atau kod dalaman "
            "seperti C4C-0001."
        )
    return text.upper()


def _read_csv(data: bytes) -> list[list]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFormatError("Fail CSV tidak dapat dibaca. Simpan sebagai UTF-8.")
    return [row for row in csv.reader(io.StringIO(text))]


def _read_xlsx(data: bytes) -> tuple[list[list], str]:
    try:
        # data_only=False: a formula cell arrives as "=..." text, which the row
        # validator rejects loudly instead of silently reading None.
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except (BadZipFile, OSError, KeyError, ValueError) as exc:
        raise ImportFormatError(
            "Fail Excel tidak dapat dibaca. Simpan semula sebagai .xlsx."
        ) from exc
    try:
        sheet = workbook.active
        if sheet is None:
            raise ImportFormatError("Fail Excel tidak mempunyai helaian.")
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        return rows, sheet.title
    finally:
        workbook.close()


def parse_upload(data: bytes, filename: str) -> ImportPreview:
    if not data:
        raise ImportFormatError("Fail kosong. Pilih fail katalog untuk diimport.")
    if len(data) > MAX_BYTES:
        raise ImportFormatError(
            f"Fail terlalu besar ({len(data) // 1024} KB). Maksimum 5 MB."
        )

    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        raw_rows, sheet_name = _read_xlsx(data)
        kind = "Excel (.xlsx)"
    elif name.endswith(".csv"):
        raw_rows, sheet_name = _read_csv(data), ""
        kind = "CSV"
    elif name.endswith((".xls", ".xlsm")):
        raise ImportFormatError(
            "Format .xls lama tidak disokong. Buka fail itu dan simpan sebagai .xlsx."
        )
    else:
        raise ImportFormatError(
            "Format fail tidak disokong. Muat naik fail .xlsx atau .csv."
        )

    if not raw_rows:
        raise ImportFormatError("Fail tidak mempunyai baris data.")

    header_row = raw_rows[0]
    mapping: dict[int, str] = {}
    unknown: list[str] = []
    for index, header in enumerate(header_row):
        if header is None or str(header).strip() == "":
            continue
        key = _key(header)
        mapped = ALIASES.get(key)
        if mapped and mapped not in mapping.values():
            mapping[index] = mapped
        elif not mapped:
            unknown.append(str(header).strip())

    missing = [required for required in ("barcode", "name") if required not in mapping.values()]
    if missing:
        labels = {"barcode": "barcode", "name": "name"}
        raise ImportFormatError(
            "Kolum wajib tiada: " + ", ".join(labels[m] for m in missing)
            + ". Muat turun templat untuk melihat susunan kolum yang betul."
        )

    preview = ImportPreview(
        unknown_columns=unknown, file_kind=kind, sheet_name=sheet_name
    )
    data_rows = raw_rows[1:]
    if len(data_rows) > MAX_ROWS:
        raise ImportFormatError(
            f"Fail mempunyai {len(data_rows)} baris. Maksimum {MAX_ROWS} baris setiap import."
        )

    seen: dict[str, int] = {}
    for offset, cells in enumerate(data_rows):
        line = offset + 2  # row 1 is the header in a spreadsheet
        values = {
            mapping[index]: cells[index]
            for index in mapping
            if index < len(cells) and _cell_text(cells[index]) != ""
        }
        if not values:
            preview.skipped_empty += 1
            continue
        preview.total_rows += 1
        try:
            row = _build_row(values, line)
        except ValueError as exc:
            preview.problems.append(RowProblem(line=line, message=str(exc)))
            continue
        barcode = row.data["barcode"]
        if barcode in seen:
            preview.problems.append(
                RowProblem(
                    line=line,
                    message=f"Kod bar {barcode} berulang (sudah ada pada baris {seen[barcode]}).",
                )
            )
            continue
        seen[barcode] = line
        preview.rows.append(row)

    return preview


def _build_row(values: dict, line: int) -> ParsedRow:
    barcode = normalise_product_code(values.get("barcode"))
    name = _clean_text(values.get("name"), "Nama", line)
    if not name:
        raise ValueError("Nama ubat wajib diisi.")

    data: dict = {"barcode": barcode, "name": name}
    for field_name in CORE_FIELDS:
        if field_name == "name":
            continue
        data[field_name] = _clean_text(values.get(field_name), field_name, line)

    extra = {}
    for field_name in EXTRA_FIELDS:
        text = _clean_text(values.get(field_name), field_name, line)
        if text:
            extra[field_name] = text
    data["extra_json"] = json.dumps(extra, ensure_ascii=False) if extra else ""

    verified_raw = _cell_text(values.get("verified")).lower()
    data["__verified__"] = verified_raw in TRUE_VALUES
    data["__source__"] = _clean_text(values.get("source"), "Sumber", line)
    return ParsedRow(line=line, data=data)


def template_workbook() -> bytes:
    """A ready-to-fill .xlsx with the expected headers and two example rows."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None  # a fresh workbook always has one
    sheet.title = "Katalog"
    headers = [column for column, _required, _hint in TEMPLATE_COLUMNS]
    sheet.append(headers)

    examples = [
        {
            "barcode": "9550019999998",
            "name": "Contoh Paracetamol 500 mg",
            "brand": "Contoh",
            "generic": "Paracetamol",
            "strength": "500 mg",
            "form": "Tablet",
            "manufacturer": "Contoh Sdn Bhd",
            "condition": "Demam & Sakit",
            "uses": "Meredakan demam dan sakit ringan.",
            "dosage": "Dewasa: 1-2 tablet setiap 4-6 jam.",
            "howToTake": "Telan dengan segelas air.",
            "warnings": "Jangan melebihi 8 tablet dalam 24 jam.",
            "sideEffects": "Jarang: ruam.",
            "storage": "Simpan di bawah 30°C.",
            "pack": "1 kotak = 10 tablet",
            "price": "6.90",
            "stock": "24",
            "expiry": "2027-06",
            "notes": "Baris contoh - ganti dengan data sebenar.",
        },
        {
            "barcode": "C4C-0001",
            "name": "Contoh Ubat Sirup 60 ml",
            "generic": "Paracetamol",
            "strength": "120 mg / 5 ml",
            "form": "Sirap",
            "uses": "Contoh baris dengan kod dalaman.",
            "notes": "Kod dalaman boleh dicari, tetapi tidak boleh diimbas kamera.",
        },
    ]
    for example in examples:
        sheet.append([example.get(column, "") for column in headers])

    widths = {"A": 18, "B": 34, "C": 16, "D": 20, "E": 12, "F": 14, "G": 26}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
