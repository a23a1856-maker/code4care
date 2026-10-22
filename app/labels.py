"""Printable test labels: barcodes and QR codes for the catalogue, as inline SVG.

Used by `/labels/test` so a pharmacy can try the scanner without a physical box of
medicine. The QR encodes the product code itself (not a URL), because the scanner
posts whatever it decodes to `/scan/lookup`.
"""
from __future__ import annotations

import io
import re

import segno
from barcode import Code128, EAN13
from barcode.writer import SVGWriter

from app.barcode import InvalidBarcode, validate_barcode

XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)


def is_ean(code: str) -> bool:
    try:
        validate_barcode(code)
        return True
    except InvalidBarcode:
        return False


def barcode_svg(code: str) -> str:
    """EAN-13 for real product barcodes, Code 128 for internal catalogue codes."""
    if is_ean(code):
        # python-barcode expects the twelve digits and computes the check digit.
        instance = EAN13(code[:12], writer=SVGWriter())
    else:
        instance = Code128(code, writer=SVGWriter())
    buffer = io.BytesIO()
    instance.write(
        buffer,
        options={
            "module_width": 0.28,
            "module_height": 12.0,
            "font_size": 9,
            "text_distance": 2.5,
            "quiet_zone": 2.5,
            "write_text": True,
        },
    )
    markup = buffer.getvalue().decode("utf-8").replace("\r\n", "\n")
    start = markup.find("<svg")
    markup = markup[start:].strip() if start >= 0 else markup.strip()
    return _mm_to_px(markup)


MM_PER_INCH = 25.4
PX_PER_INCH = 96.0
MM_TO_PX = PX_PER_INCH / MM_PER_INCH


def _mm_to_px(markup: str) -> str:
    """python-barcode writes millimetres and no viewBox, which CSS scaling breaks.

    Converting every millimetre to CSS pixels (96 dpi) and adding a viewBox lets
    the label scale to any card width while keeping the bars and text proportional.
    """
    root = re.search(r'width="([\d.]+)mm"\s+height="([\d.]+)mm"', markup)
    if not root:
        return markup
    width_mm, height_mm = float(root.group(1)), float(root.group(2))
    markup = re.sub(
        r'"([\d.]+)mm"',
        lambda match: f'"{float(match.group(1)) * MM_TO_PX:.2f}"',
        markup,
    )
    view_box = f'viewBox="0 0 {width_mm * MM_TO_PX:.2f} {height_mm * MM_TO_PX:.2f}"'
    markup = markup.replace(
        "<svg ", f'<svg {view_box} preserveAspectRatio="xMidYMid meet" ', 1
    )
    # Our CSP (style-src 'self') ignores inline style attributes, which would turn
    # every fill black; turn them into presentation attributes instead.
    return STYLE_ATTRIBUTE.sub(_style_to_attributes, markup)


STYLE_ATTRIBUTE = re.compile(r'style="([^"]*)"')


def _style_to_attributes(match: re.Match) -> str:
    parts = []
    for declaration in match.group(1).split(";"):
        if ":" not in declaration:
            continue
        prop, value = (piece.strip() for piece in declaration.split(":", 1))
        if prop == "fill":
            parts.append(f'fill="{value}"')
        elif prop == "font-size" and value.endswith("pt"):
            parts.append(f'font-size="{float(value[:-2]) * 96 / 72:.2f}"')
        elif prop in ("text-anchor", "stroke", "stroke-width"):
            parts.append(f'{prop}="{value}"')
    return " ".join(parts)


def qr_code(text: str):
    """A standard QR code, never a Micro QR (cameras often cannot read those)."""
    return segno.make(text, error="h", micro=False)


def qr_svg(text: str) -> str:
    """A QR code whose whole content is the product code.

    border=3 keeps a proper quiet zone, which scanners need; a single-module
    border is often too tight for a phone.
    """
    return qr_code(text).svg_inline(
        scale=5, border=3, dark="#12302b", light="#ffffff"
    )


def label_item(medicine: dict) -> dict:
    code = str(medicine["barcode"])
    return {
        "medicine": medicine,
        "code": code,
        "kind": "EAN-13" if is_ean(code) else "Code 128",
        "barcode_svg": barcode_svg(code),
        "qr_svg": qr_svg(code),
    }
