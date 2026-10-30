"""Turn an extraction into a trustworthy, flagged, scored order.

Signal hierarchy (strongest first) — this ordering is the core of the accuracy
story we sell:

1. arithmetic identity        qty x unit_price == extended_price, sum == total
2. reference-data match       crosswalk hit / price list / UOM list
3. evidence verification      the quoted text really exists on that page
4. page quality               scan vs text layer, rotation applied, handwriting
5. model self-report          weakest; only ever lowers confidence
"""

from __future__ import annotations

import re
from decimal import Decimal

from .matching import (
    ITEM_DESC_AUTO,
    ITEM_DESC_REVIEW,
    SHIP_TO_AUTO,
    SHIP_TO_REVIEW,
    ReferenceData,
)
from .normalize import canonical_uom, decimal_or_none, normalize_text, parse_date
from .pdfutil import Document
from .schema import (
    Evidence,
    ExtractionResult,
    Flag,
    FlagCode,
    LineItem,
    MailEnvelope,
    OrderAssessment,
    PageRole,
    ResolvedLine,
    Severity,
)

# Confidence ceilings. A model reading a 200-dpi fax cannot be as certain as one
# reading a text-layer PDF, so we hard-cap what the pipeline can claim. These
# numbers come from the acceptance runs in docs/02_architecture.md and are the
# knobs the client tunes once we have their own sample set.
CEILING_HANDWRITTEN = 0.85
CEILING_SCANNED = 0.93
CEILING_FAX_QUALITY = 0.88

PRICE_TOLERANCE = Decimal("0.005")   # absolute; contract prices are exact
PRICE_REL_TOLERANCE = Decimal("0.0005")  # 0.05%: absorbs rounding in extended price


def _money(d: Decimal | None) -> str | None:
    return None if d is None else f"{d:.2f}"


def _q(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _evidence_verified(evidence: Evidence | None, doc: Document) -> bool | None:
    """True/False when the page has a text layer we can search, None when not."""
    if evidence is None or not evidence.quote:
        return None
    try:
        text = doc.page_view(evidence.page).text
    except Exception:
        return None
    if not text.strip():
        return None
    return _q(evidence.quote)[:60] in _q(text)


def assess(
    extraction: ExtractionResult,
    env: MailEnvelope,
    doc: Document,
    ref: ReferenceData,
    order_id: str,
    pages: list | None = None,
) -> OrderAssessment:
    order = extraction.order
    flags: list[Flag] = []
    confidence: dict[str, float] = {}

    def add(code: FlagCode, sev: Severity, field: str | None, msg: str, **kw) -> None:
        flags.append(Flag(code=code, severity=sev, field=field, message=msg, **kw))

    # ---------------- page-level quality -------------------------------- #
    pages = pages or []
    po_pages = [p for p in pages if p.role in (PageRole.PO, PageRole.PO_CONTINUATION)]
    scanned = [p.page_no for p in po_pages if p.is_probably_scanned]
    rotated = [p.page_no for p in po_pages if p.rotation_applied]
    ceiling = 1.0

    if rotated:
        add(
            FlagCode.DOC_LOW_QUALITY,
            Severity.INFO,
            f"page {', '.join(str(n) for n in rotated)}",
            f"Page(s) arrived rotated by {'/'.join(str(p.rotation_applied) for p in po_pages if p.rotation_applied)} degrees; corrected automatically.",
        )
    if scanned:
        add(
            FlagCode.DOC_LOW_QUALITY,
            Severity.REVIEW,
            f"page {', '.join(str(n) for n in scanned)}",
            "Order page is a scan/fax image with no text layer — values read by vision only.",
        )
        ceiling = min(ceiling, CEILING_SCANNED)
    for page_no in extraction.handwritten_pages:
        add(FlagCode.HANDWRITTEN, Severity.REVIEW, f"page {page_no}", "Hand-written page; values need a human eye.")
        ceiling = min(ceiling, CEILING_HANDWRITTEN)

    # ---------------- evidence verification ------------------------------ #
    unverified: list[str] = []
    for field, ev in extraction.evidence.items():
        ok = _evidence_verified(ev, doc)
        if ok is False:
            unverified.append(field)
    if unverified:
        add(
            FlagCode.EVIDENCE_UNVERIFIED,
            Severity.REVIEW,
            ", ".join(unverified[:6]),
            "Model cited text that could not be found on the page — treat these values as suspect.",
        )

    # ---------------- identity ------------------------------------------ #
    if not order.po_number:
        add(FlagCode.MISSING_PO_NUMBER, Severity.BLOCK, "po_number", "No PO number on the document.")
    elif not re.search(r"[A-Z0-9]", order.po_number.upper()):
        add(FlagCode.MISSING_PO_NUMBER, Severity.BLOCK, "po_number", "PO number is not a usable value.")
    confidence["po_number"] = 0.99 if order.po_number else 0.0

    # ---------------- customer ------------------------------------------ #
    cust_id, cust_score, cust_method, cust_rivals = ref.match_customer(
        env.sender_email, order.customer_name, order.bill_to
    )
    if cust_id is None:
        if cust_rivals:
            add(
                FlagCode.CUSTOMER_AMBIGUOUS,
                Severity.BLOCK,
                "customer",
                "Printed customer matches more than one account.",
                extracted=order.customer_name,
                reference=" | ".join(cust_rivals),
            )
        else:
            add(
                FlagCode.CUSTOMER_NOT_FOUND,
                Severity.BLOCK,
                "customer",
                "Sender and printed name did not resolve to any customer account.",
                extracted=order.customer_name or env.sender_email,
            )
        confidence["customer"] = 0.0
    else:
        confidence["customer"] = min(1.0, cust_score / 100)

    # ---------------- ship-to ------------------------------------------- #
    ship_to_id, st_score, st_method, st_rivals = ref.match_ship_to(cust_id, order.ship_to)
    if st_score < SHIP_TO_REVIEW:
        add(
            FlagCode.SHIP_TO_NOT_FOUND,
            Severity.REVIEW if cust_id else Severity.BLOCK,
            "ship_to",
            "Ship-to address did not match any address on this customer's account.",
            extracted=", ".join(filter(None, [order.ship_to.street, order.ship_to.city, order.ship_to.zip])),
        )
        confidence["ship_to"] = 0.2
    elif st_score < SHIP_TO_AUTO or st_rivals:
        add(
            FlagCode.SHIP_TO_AMBIGUOUS,
            Severity.REVIEW,
            "ship_to",
            f"Ship-to match is close but not certain (score {st_score:.0f}).",
            reference=ship_to_id,
        )
        confidence["ship_to"] = 0.6
    else:
        confidence["ship_to"] = min(1.0, st_score / 100)

    # ---------------- dates --------------------------------------------- #
    order_date, ambiguous_date = parse_date(order.order_date)
    if ambiguous_date:
        add(FlagCode.DATE_AMBIGUOUS, Severity.INFO, "order_date", "Date could be D/M or M/D; assumed US format.")
        confidence["order_date"] = 0.7
    else:
        confidence["order_date"] = 0.99 if order_date else 0.0

    # ---------------- lines --------------------------------------------- #
    resolved: list[ResolvedLine] = []
    if not order.line_items:
        add(FlagCode.MISSING_REQUIRED_FIELD, Severity.BLOCK, "line_items", "No line items extracted.")

    for idx, line in enumerate(order.line_items):
        path = f"line_items[{idx}]"
        rl = ResolvedLine(line_no=line.line_no or idx + 1, extracted=line)
        conf_parts: list[float] = []

        if line.qty is None or line.qty <= 0:
            rl.flags.append(_f(FlagCode.MISSING_REQUIRED_FIELD, Severity.BLOCK, f"{path}.qty", "Quantity missing or zero."))
            conf_parts.append(0.0)
        else:
            conf_parts.append(0.98)

        match = ref.match_item(cust_id, line.customer_item_no, line.description)
        rl.match_method = match["method"]
        rl.match_score = float(match["score"])
        if match["sku"]:
            rl.sku = match["sku"]
            item = ref.items[match["sku"]]
            rl.erp_description = item.description
            rl.erp_uom = canonical_uom(item.uom)[0] or item.uom
            rl.erp_price = item.price
            conf_parts.append(1.0 if rl.match_method != "description" else min(1.0, rl.match_score / 100))
            if rl.match_method == "description":
                rl.flags.append(
                    _f(
                        FlagCode.ITEM_MATCHED_BY_DESCRIPTION,
                        Severity.REVIEW,
                        f"{path}.customer_item_no",
                        f"No part-number match; description matched {rl.sku} at {rl.match_score:.0f}%.",
                        extracted=line.description,
                        reference=f"{rl.sku} — {rl.erp_description}",
                    )
                )
        elif match["method"].endswith("ambiguous"):
            rl.flags.append(
                _f(
                    FlagCode.ITEM_AMBIGUOUS,
                    Severity.BLOCK,
                    f"{path}.customer_item_no",
                    "More than one catalogue item fits this line.",
                    extracted=line.customer_item_no or line.description,
                    reference=" | ".join(match["candidates"]),
                )
            )
            conf_parts.append(0.1)
        else:
            rl.flags.append(
                _f(
                    FlagCode.ITEM_NOT_FOUND,
                    Severity.BLOCK,
                    f"{path}.customer_item_no",
                    "Part number and description did not resolve to an active item.",
                    extracted=line.customer_item_no or line.description,
                )
            )
            conf_parts.append(0.0)

        # UOM
        uom, mapped = canonical_uom(line.uom)
        rl.uom = uom
        if line.uom and not mapped:
            rl.flags.append(
                _f(FlagCode.UOM_UNMAPPED, Severity.REVIEW, f"{path}.uom", f"UOM '{line.uom}' is not in the mapping table.")
            )
            conf_parts.append(0.4)
        if rl.erp_uom and uom and uom != rl.erp_uom:
            rl.flags.append(
                _f(
                    FlagCode.UOM_MISMATCH,
                    Severity.BLOCK,
                    f"{path}.uom",
                    "Unit of measure differs from the ERP item's UOM — quantity may be wrong.",
                    extracted=line.uom,
                    reference=rl.erp_uom,
                )
            )
            conf_parts.append(0.2)
        elif rl.erp_uom:
            conf_parts.append(0.98)

        # price
        price = decimal_or_none(line.unit_price)
        if price is None:
            if rl.erp_price is not None:
                rl.flags.append(
                    _f(
                        FlagCode.PRICE_MISSING,
                        Severity.REVIEW,
                        f"{path}.unit_price",
                        "No price printed; ERP list price suggested for the rep.",
                        reference=_money(rl.erp_price),
                    )
                )
            rl.unit_price = rl.erp_price
            conf_parts.append(0.5)
        else:
            rl.unit_price = price
            if rl.erp_price is not None:
                delta = price - rl.erp_price
                tol = max(PRICE_TOLERANCE, abs(rl.erp_price) * PRICE_REL_TOLERANCE)
                if abs(delta) > tol:
                    pct = (delta / rl.erp_price * 100) if rl.erp_price else Decimal(0)
                    rl.flags.append(
                        _f(
                            FlagCode.PRICE_MISMATCH,
                            Severity.REVIEW,
                            f"{path}.unit_price",
                            f"Printed price differs from ERP by {pct:+.2f}%.",
                            extracted=_money(price),
                            reference=_money(rl.erp_price),
                        )
                    )
                    conf_parts.append(0.3)
                else:
                    conf_parts.append(0.99)
            else:
                conf_parts.append(0.6)

        # arithmetic
        ext = decimal_or_none(line.extended_price)
        if ext is not None and price is not None and line.qty is not None:
            expected = (price * line.qty).quantize(Decimal("0.01"))
            if abs(expected - ext) > Decimal("0.02"):
                rl.flags.append(
                    _f(
                        FlagCode.LINE_ARITHMETIC,
                        Severity.REVIEW,
                        f"{path}.extended_price",
                        "Qty x unit price does not equal the printed extended price.",
                        extracted=_money(ext),
                        reference=_money(expected),
                    )
                )
                conf_parts.append(0.3)
            else:
                conf_parts.append(1.0)

        flags.extend(rl.flags)
        confidence[f"{path}"] = round(min(conf_parts) if conf_parts else 0.5, 3)
        resolved.append(rl)

    # ---------------- totals -------------------------------------------- #
    total = decimal_or_none(order.total)
    if total is not None and resolved:
        lines_sum = sum(
            (decimal_or_none(l.extracted.extended_price) or (l.unit_price or Decimal(0)) * (l.extracted.qty or Decimal(0)))
            for l in resolved
        )
        extras = sum(filter(None, [decimal_or_none(order.freight), decimal_or_none(order.tax)])) or Decimal(0)
        expected = (lines_sum + Decimal(extras)).quantize(Decimal("0.01"))
        if abs(expected - total) > Decimal("0.05"):
            add(
                FlagCode.TOTAL_MISMATCH,
                Severity.REVIEW,
                "total",
                "Sum of lines (+ freight/tax) does not equal the printed total — a line may be missing a page.",
                extracted=_money(total),
                reference=_money(expected),
            )
            confidence["total"] = 0.3
        else:
            confidence["total"] = 0.99
    else:
        confidence["total"] = 0.85 if total is None else 0.99

    # ---------------- shipping instructions ------------------------------ #
    if order.carrier_account:
        confidence["carrier_account"] = 0.95
    if order.special_instructions:
        confidence["special_instructions"] = 0.9

    # ---------------- aggregate ------------------------------------------ #
    weights = {"customer": 0.25, "ship_to": 0.15, "po_number": 0.1}
    line_weights = [v for k, v in confidence.items() if k.startswith("line_items[")]
    weighted = sum(confidence[k] * w for k, w in weights.items() if k in confidence)
    weight_total = sum(w for k, w in weights.items() if k in confidence)
    if line_weights:
        weighted += (sum(line_weights) / len(line_weights)) * 0.5
        weight_total += 0.5
    order_conf = round(weighted / weight_total, 3) if weight_total else 0.0

    if unverified:
        order_conf = round(order_conf * 0.85, 3)
    if ceiling < 1.0:
        order_conf = round(min(order_conf, ceiling), 3)

    blocking = [f for f in flags if f.severity is Severity.BLOCK]
    review = [f for f in flags if f.severity is Severity.REVIEW]
    if blocking:
        route = "blocked"
    elif review or order_conf < 0.92:
        route = "needs_review"
    else:
        route = "auto_ready"

    return OrderAssessment(
        order_id=order_id,
        source_message_id=env.message_id,
        source_filename=doc.path.name,
        extraction=extraction,
        resolved_lines=resolved,
        customer_id=cust_id,
        customer_name=ref.customers[cust_id].name if cust_id else order.customer_name,
        ship_to_id=ship_to_id if st_score >= SHIP_TO_AUTO and not st_rivals else None,
        flags=flags,
        field_confidence=confidence,
        order_confidence=order_conf,
        route=route,  # type: ignore[arg-type]
    )


def _f(code: FlagCode, sev: Severity, field: str, msg: str, **kw) -> Flag:
    return Flag(code=code, severity=sev, field=field, message=msg, **kw)


def item_confidence_note(score: float, method: str) -> str:
    if method == "description":
        if score >= ITEM_DESC_AUTO:
            return "auto"
        if score >= ITEM_DESC_REVIEW:
            return "review"
    return "exact" if score >= 100 else "review"

