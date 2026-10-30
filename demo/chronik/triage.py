"""Page-level triage: which pages are worth paying a vision model for.

Cost control matters more than elegance here. A 12-page fax that is 1 page of
order + 1 page of continuation + 10 pages of legal boilerplate must not cost 12
vision calls.
"""

from __future__ import annotations

import re

from .pdfutil import PageView
from .schema import PageInfo, PageRole, PageRoleHint

_TERMS = re.compile(
    r"TERMS\s+AND\s+CONDITIONS|TERMS\s+OF\s+SALE|SHALL\s+BE\s+GOVERNED"
    r"|LIMITATION\s+OF\s+LIABILITY|WARRANT(?:Y|IES)\s+(?:OF|AND)|INDEMNIF",
    re.I,
)
_COVER = re.compile(r"FAX\s+(?:COVER|TRANSMITTAL)|COVER\s+(?:SHEET|PAGE)", re.I)
_PACKING = re.compile(r"PACKING\s+(?:SLIP|LIST)", re.I)
_PO = re.compile(
    r"PURCHASE\s+ORDER|PURCHASE\s+REQUISITION|REQUISITION|ORDER\s+FORM"
    r"|\bP\.?\s?O\.?\s*(?:NUMBER|NO\.?|#)\b",
    re.I,
)
_TABLE = re.compile(
    r"\b(QTY|QUANTITY|ORDERED)\b.{0,90}\b(ITEM|DESCRIPTION|PART|PRODUCT|SKU)\b"
    r"|\bUNIT\s+PRICE\b|\bEXT\.?\s*(?:PRICE|AMOUNT)\b|\bPRICE\s+EA\b",
    re.I | re.S,
)
_AMOUNT = re.compile(r"\b\d[\d,]*\.\d{2}\b")
_CONT = re.compile(r"PURCHASE\s+ORDER\s*\(?CONT|CONTINUED|PAGE\s+\d+\s+OF\s+\d+", re.I)


def classify_page(view: PageView) -> PageRole:
    text = view.text or ""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 25 and view.image_count <= 1 and not compact:
        return PageRole.BLANK
    if _COVER.search(compact):
        return PageRole.COVER
    if _PACKING.search(compact):
        return PageRole.PACKING_SLIP
    if _TERMS.search(compact):
        return PageRole.TERMS
    money_rows = len(_AMOUNT.findall(compact))
    if _PO.search(compact) or _TABLE.search(compact) or money_rows >= 3:
        if _CONT.search(compact) and not _PO.search(compact):
            return PageRole.PO_CONTINUATION
        return PageRole.PO
    return PageRole.OTHER


def triage(views: list[PageView], vision_hints: dict[int, PageRoleHint] | None = None) -> list[PageInfo]:
    """Classify every page.

    ``vision_hints`` lets a cheap classifier model override rule-based triage for
    pages without a text layer (scans, faxes) — those are the only pages that
    ever need a paid call at this stage.
    """
    out: list[PageInfo] = []
    for v in views:
        hint = vision_hints.get(v.page_no) if vision_hints else None
        if hint is not None:
            role, rotation = hint.role, hint.rotation
        elif v.has_text_layer:
            role, rotation = classify_page(v), 0
        else:
            # image-only page and no classifier available: assume it matters
            role, rotation = PageRole.OTHER, 0
        out.append(
            PageInfo(
                page_no=v.page_no,
                role=role,
                rotation_applied=rotation,
                has_text_layer=v.has_text_layer,
                char_count=len(v.text.strip()),
                is_probably_scanned=not v.has_text_layer and v.image_count > 0,
                low_quality=not v.has_text_layer and v.image_count > 0,
            )
        )
    return out


def pages_to_extract(pages: list[PageInfo]) -> list[int]:
    return [p.page_no for p in pages if p.role in (PageRole.PO, PageRole.PO_CONTINUATION)]
