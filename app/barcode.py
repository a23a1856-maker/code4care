"""Barcode validation, before any value reaches the database."""
from __future__ import annotations

import re

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 64
MAX_BARCODE_LENGTH = 32
EAN_LENGTHS = (8, 12, 13)


class InvalidBarcode(ValueError):
    """Invalid input: the route shows this message and saves nothing."""


def _check_digit_ok(code: str) -> bool:
    body, check = code[:-1], int(code[-1])
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(body))
    )
    return (10 - total % 10) % 10 == check


def validate_barcode(raw: str | None) -> str:
    """Return the normalised barcode or raise InvalidBarcode with a clear message.

    Medicine packaging in Malaysia uses EAN-8, UPC-A (12) or EAN-13; anything
    else is refused rather than searched for, so a stray keystroke or a pasted
    sentence never reaches the database.
    """
    value = (raw or "").strip()
    if not value:
        raise InvalidBarcode("Kod bar tidak sah. Masukkan kod bar terlebih dahulu.")
    if len(value) > MAX_BARCODE_LENGTH:
        raise InvalidBarcode("Kod bar tidak sah. Kod bar terlalu panjang (maksimum 32 aksara).")
    if not value.isdigit():
        raise InvalidBarcode(
            "Kod bar tidak sah. Kod bar mesti mengandungi digit sahaja (8, 12 atau 13 digit)."
        )
    if len(value) not in EAN_LENGTHS:
        raise InvalidBarcode(
            "Kod bar tidak sah. Kod bar nombor mesti 8, 12 atau 13 digit."
        )
    if not _check_digit_ok(value):
        raise InvalidBarcode("Kod bar tidak sah. Sila semak semula nombor dan cuba lagi.")
    return value


def normalize_query(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) < MIN_QUERY_LENGTH:
        raise InvalidBarcode("Kod bar tidak sah. Masukkan sekurang-kurangnya 2 aksara.")
    if len(value) > MAX_QUERY_LENGTH:
        raise InvalidBarcode("Kod bar tidak sah. Carian terlalu panjang (maksimum 64 aksara).")
    return value


def request_key(raw: str | None) -> str | None:
    """A repeat of the same client request key must not save twice."""
    value = (raw or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", value):
        return None
    return value
