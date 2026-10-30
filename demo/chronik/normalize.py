"""Normalisation helpers: the boring code that decides whether matching works."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# UOM is the single most under-estimated source of wrong orders in distribution.
# We map to a canonical code list; anything not in the map is *flagged*, never
# guessed (EA vs BX vs CS is a real quantity difference, not a cosmetic one).
_CANONICAL_UOM = {
    "EA": "EA", "EACH": "EA", "E": "EA", "UNIT": "EA", "UN": "EA", "UNITS": "EA",
    "BX": "BX", "BOX": "BX", "BOXES": "BX",
    "CS": "CS", "CASE": "CS", "CASES": "CS",
    "PK": "PK", "PACK": "PK", "PACKS": "PK", "PAK": "PK",
    "DZ": "DZ", "DOZ": "DZ", "DOZEN": "DZ",
    "PR": "PR", "PAIR": "PR", "PAIRS": "PR",
    "RL": "RL", "ROLL": "RL", "ROLLS": "RL",
    "GL": "GL", "GAL": "GL", "GALLON": "GL",
    "LB": "LB", "LBS": "LB", "POUND": "LB",
    "KG": "KG", "OZ": "OZ", "BT": "BT", "BTL": "BT", "BOTTLE": "BT",
    "TB": "TB", "TUBE": "TB", "BG": "BG", "BAG": "BG",
}


def canonical_uom(raw: str | None) -> tuple[str | None, bool]:
    """Return (canonical, mapped?). ``mapped=False`` means a human must look."""
    if raw is None:
        return None, False
    key = re.sub(r"[^A-Z]", "", raw.upper())
    if not key:
        return None, False
    if key in _CANONICAL_UOM:
        return _CANONICAL_UOM[key], True
    return key[:3], False


def sku_key(raw: str | None) -> str:
    """Aggressive key for *comparison only*: '12-345 A' == '12345A'."""
    if not raw:
        return ""
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def decimal_or_none(raw) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    cleaned = re.sub(r"[^\d.\-]", "", str(raw).replace(",", ""))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.0001")).normalize()
    except InvalidOperation:
        return None


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%m-%d-%Y", "%Y/%m/%d", "%d %b %Y")


def parse_date(raw) -> tuple[date | None, bool]:
    """Return (date, ambiguous). Ambiguity = both day and month <= 12."""
    if raw is None or raw == "":
        return None, False
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw, False
    s = str(raw).strip()
    ambiguous = False
    md = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", s)
    if md and int(md.group(1)) <= 12 and int(md.group(2)) <= 12:
        ambiguous = True
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date(), ambiguous
        except ValueError:
            continue
    return None, ambiguous


def normalize_text(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.upper()
    s = re.sub(r"&", " AND ", s)
    s = re.sub(r"\b(INC|LLC|LTD|CO|CORP|COMPANY|INCORPORATED)\b\.?", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_street(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.upper()
    repl = {
        r"\bSTREET\b": "ST", r"\bAVENUE\b": "AVE", r"\bROAD\b": "RD", r"\bDRIVE\b": "DR",
        r"\bBOULEVARD\b": "BLVD", r"\bSUITE\b": "STE", r"\bHIGHWAY\b": "HWY",
        r"\bNORTH\b": "N", r"\bSOUTH\b": "S", r"\bEAST\b": "E", r"\bWEST\b": "W",
        r"\bPARKWAY\b": "PKWY", r"\bLANE\b": "LN", r"\bCOURT\b": "CT",
    }
    for pat, rep in repl.items():
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_zip(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"[^0-9]", "", str(raw))[:5]
