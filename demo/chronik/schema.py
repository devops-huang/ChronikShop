"""Canonical data model for the PO agent.

Design notes
------------
* Everything the model produces is *plain data* (no confidence baked into each
  field). Confidence/flags are computed afterwards by deterministic code
  (see :mod:`chronik.validate` and :mod:`chronik.confidence`), because a model's
  self-reported confidence is a weak signal while arithmetic / reference-data
  checks are strong ones.
* ``evidence`` maps a JSON pointer-ish field path (``line_items[0].unit_price``)
  to the page + quote the value was read from. This is what lets a rep click a
  flag and see the exact spot on the fax, and it also lets us mechanically
  verify that the model did not hallucinate a value.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# email / attachment envelope
# --------------------------------------------------------------------------- #
class AttachmentRef(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    local_path: str | None = None


class MailEnvelope(BaseModel):
    """Normalised view over Microsoft Graph message (or a Front webhook)."""

    message_id: str
    received_at: datetime
    sender_email: str
    subject: str = ""
    body_text: str = ""
    attachments: list[AttachmentRef] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# page triage
# --------------------------------------------------------------------------- #
class PageRole(str, Enum):
    PO = "po"                      # order header and/or line items
    PO_CONTINUATION = "po_continuation"
    COVER = "cover"                # fax / email cover sheet
    TERMS = "terms"                # T&C, legal boilerplate
    PACKING_SLIP = "packing_slip"
    BLANK = "blank"
    OTHER = "other"


class PageInfo(BaseModel):
    page_no: int                     # 1-based
    role: PageRole = PageRole.OTHER
    rotation_applied: int = 0        # degrees we had to rotate to make it upright
    has_text_layer: bool = False
    char_count: int = 0
    image_dpi_estimate: int | None = None
    is_probably_scanned: bool = False
    low_quality: bool = False        # fax speckle / heavy skew / very low dpi


# --------------------------------------------------------------------------- #
# extraction payload (what the model is asked to return)
# --------------------------------------------------------------------------- #
class Party(BaseModel):
    name: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    contact: str | None = None


class LineItem(BaseModel):
    line_no: int | None = None
    customer_item_no: str | None = None
    description: str | None = None
    qty: Decimal | None = None
    uom: str | None = None
    unit_price: Decimal | None = None
    extended_price: Decimal | None = None
    requested_date: date | None = None
    notes: str | None = None


class ExtractedOrder(BaseModel):
    po_number: str | None = None
    order_date: date | None = None
    customer_name: str | None = None
    bill_to: Party = Field(default_factory=Party)
    ship_to: Party = Field(default_factory=Party)
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    freight: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = "USD"
    ship_via: str | None = None
    carrier_account: str | None = None
    freight_terms: str | None = None
    requested_ship_date: date | None = None
    special_instructions: str | None = None


class Evidence(BaseModel):
    page: int
    quote: str | None = None
    # normalised [x0, y0, x1, y1] in 0..1 page coordinates. For scanned pages we
    # cannot search a text layer, and shipping Tesseract into the customer's
    # environment just to draw a highlight is not worth it — the vision model
    # already knows where it read the value, so we ask it.
    bbox: list[float] | None = None
    note: str | None = None


class PageRoleHint(BaseModel):
    role: PageRole
    rotation: int = 0


class ExtractionResult(BaseModel):
    order: ExtractedOrder
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    # signals the extractor itself is confident about (weak, but free)
    model_notes: list[str] = Field(default_factory=list)
    handwritten_pages: list[int] = Field(default_factory=list)
    provider: str = "unknown"
    model: str = "unknown"
    prompt_version: str = "v0"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


# --------------------------------------------------------------------------- #
# matching / validation output
# --------------------------------------------------------------------------- #
class FlagCode(str, Enum):
    MISSING_PO_NUMBER = "MISSING_PO_NUMBER"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    CUSTOMER_AMBIGUOUS = "CUSTOMER_AMBIGUOUS"
    SHIP_TO_NOT_FOUND = "SHIP_TO_NOT_FOUND"
    SHIP_TO_AMBIGUOUS = "SHIP_TO_AMBIGUOUS"
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    ITEM_AMBIGUOUS = "ITEM_AMBIGUOUS"
    ITEM_MATCHED_BY_DESCRIPTION = "ITEM_MATCHED_BY_DESCRIPTION"
    UOM_UNMAPPED = "UOM_UNMAPPED"
    UOM_MISMATCH = "UOM_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    PRICE_MISSING = "PRICE_MISSING"
    LINE_ARITHMETIC = "LINE_ARITHMETIC"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    DATE_AMBIGUOUS = "DATE_AMBIGUOUS"
    DOC_LOW_QUALITY = "DOC_LOW_QUALITY"
    HANDWRITTEN = "HANDWRITTEN"
    EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"


class Severity(str, Enum):
    BLOCK = "block"     # cannot be imported without a human fixing it
    REVIEW = "review"   # importable but a rep must look
    INFO = "info"       # tracked, no action


class Flag(BaseModel):
    code: FlagCode
    severity: Severity
    field: str | None = None      # e.g. "line_items[1].unit_price"
    message: str = ""
    extracted: str | None = None
    reference: str | None = None


class ResolvedLine(BaseModel):
    line_no: int | None
    extracted: LineItem
    sku: str | None = None
    erp_description: str | None = None
    erp_uom: str | None = None
    erp_price: Decimal | None = None
    uom: str | None = None                 # canonical UOM we will emit
    unit_price: Decimal | None = None      # price we will emit
    match_method: str = "none"             # customer_part|legacy_part|sku|description|none
    match_score: float = 0.0
    flags: list[Flag] = Field(default_factory=list)


class OrderAssessment(BaseModel):
    """The unit the CSV writer and the review sheet consume."""

    order_id: str                          # internal id (stable, also the filename stem)
    source_message_id: str
    source_filename: str
    extraction: ExtractionResult
    resolved_lines: list[ResolvedLine] = Field(default_factory=list)
    customer_id: str | None = None
    customer_name: str | None = None
    ship_to_id: str | None = None
    flags: list[Flag] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    order_confidence: float = 1.0
    route: Literal["auto_ready", "needs_review", "blocked"] = "needs_review"
    pages: list[PageInfo] = Field(default_factory=list)

    @property
    def blocking(self) -> list[Flag]:
        return [f for f in self.flags if f.severity is Severity.BLOCK]
