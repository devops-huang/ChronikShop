"""Build the sample documents used by the demo.

Everything here is **synthetic** — invented customers, items and addresses.
No client data is involved. The four samples deliberately cover the four
document classes the brief calls out:

    clean_po.pdf          born-digital, modern layout, 1 page
    fax_multipage.pdf     300-dpi fax look: cover sheet + rotated PO + continuation + T&C
    handwritten_po.pdf    rough handwriting-look form, several illegible fields
    unknown_format.pdf    a customer format nobody has seen: 2 pages, odd labels,
                          unit-of-measure in a free-text column, missing PO number

Run:  python -m samples.build_samples
"""

from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib.pagesizes import LETTER, legal
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent
# a hand-writing-ish font stack: fall back gracefully if not installed
HAND_FONTS = ["Bradley Hand", "Segoe Script", "Comic Sans MS", "Helvetica-Oblique"]

random.seed(7)


def _p(c: canvas.Canvas, x, y, text, size=9, font="Helvetica", **kw):
    c.setFont(font, size)
    c.drawString(x, y, text)


# --------------------------------------------------------------------------- #
# 1. clean system-generated PO
# --------------------------------------------------------------------------- #
def clean_po(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER
    _p(c, inch, h - 0.8 * inch, "NORTHGATE SURGICAL SUPPLY, LLC", 14, "Helvetica-Bold")
    _p(c, inch, h - 1.0 * inch, "1420 Meridian Parkway, Suite 300, Columbus, OH 43219", 8)
    _p(c, 5.6 * inch, h - 0.8 * inch, "PURCHASE ORDER", 13, "Helvetica-Bold")
    meta = [
        ("PO Number:", "NG-4471902"),
        ("Order Date:", "09/12/2025"),
        ("Terms:", "Net 30"),
        ("Buyer:", "Dana Whitfield"),
    ]
    y = h - 1.35 * inch
    for k, v in meta:
        _p(c, 5.6 * inch, y, k, 8)
        _p(c, 6.55 * inch, y, v, 8, "Helvetica-Bold")
        y -= 0.17 * inch

    _p(c, inch, h - 1.45 * inch, "SHIP TO", 8, "Helvetica-Bold")
    for i, line in enumerate(
        ["Riverside Regional Medical Center", "Attn: Central Supply", "900 Beacon Street, Dock 4",
         "Springfield, IL 62704"]
    ):
        _p(c, inch, h - 1.62 * inch - i * 0.15 * inch, line, 8)

    _p(c, inch, h - 2.45 * inch, "BILL TO", 8, "Helvetica-Bold")
    for i, line in enumerate(["Northgate Surgical Supply, LLC", "Accounts Payable", "PO Box 88231", "Columbus, OH 43219"]):
        _p(c, inch, h - 2.62 * inch - i * 0.15 * inch, line, 8)

    _p(c, inch, h - 3.35 * inch, "SHIPPING INSTRUCTIONS", 8, "Helvetica-Bold")
    _p(c, inch, h - 3.5 * inch, "Ship via FedEx Ground, bill freight to our account 4218-9930-7. Deliver 7am-2pm only.", 7.5)

    # table
    top = h - 3.95 * inch
    cols = [inch, 1.35 * inch, 2.05 * inch, 4.75 * inch, 5.45 * inch, 6.15 * inch, 7.05 * inch]
    heads = ["LINE", "CUST ITEM", "MANUFACTURER #", "DESCRIPTION", "QTY", "UOM", "UNIT PRICE", "EXT PRICE"]
    c.setLineWidth(0.7)
    c.line(inch, top, w - inch, top)
    for x, hd in zip(cols, heads):
        _p(c, x, top - 12, hd, 7.5, "Helvetica-Bold")
    c.line(inch, top - 16, w - inch, top - 16)

    rows = [
        ("1", "NG-10042", "MD-5521", "Sterile gauze sponge, 4x4, 12-ply, 25/bx", "48", "BX", "18.40"),
        ("2", "NG-10077", "MD-5521-NS", "Non-sterile gauze sponge, 4x4, 200/bg", "12", "BG", "27.85"),
        ("3", "NG-33120", "SG-9910", "Nitrile exam gloves, powder-free, medium, 100/bx", "60", "BX", "9.75"),
        ("4", "NG-33455", "SG-9910-L", "Nitrile exam gloves, powder-free, large, 100/bx", "40", "BX", "9.75"),
        ("5", "NG-88010", "TS-4410", "Surgical tape, paper, 1in x 10yd, 12/bx", "25", "BX", "6.20"),
        ("6", "NG-90233", "IV-2200", "IV administration set, 20 drop, 50/cs", "8", "CS", "63.40"),
    ]
    y = top - 30
    ext_total = 0.0
    for r in rows:
        for x, val in zip(cols, r):
            _p(c, x, y, val, 8)
        qty, price = float(r[4]), float(r[6])
        ext_total += round(qty * price, 2)
        _p(c, 7.05 * inch, y, f"{qty * price:,.2f}", 8)
        y -= 0.2 * inch

    c.line(inch, y + 6, w - inch, y + 6)
    y -= 12
    _p(c, 5.9 * inch, y, "Subtotal:", 8)
    _p(c, 7.05 * inch, y, f"{ext_total:,.2f}", 8)
    _p(c, 5.9 * inch, y - 14, "Freight:", 8)
    _p(c, 7.05 * inch, y - 14, "38.50", 8)
    _p(c, 5.9 * inch, y - 28, "TOTAL:", 8, "Helvetica-Bold")
    _p(c, 7.05 * inch, y - 28, f"{ext_total + 38.5:,.2f}", 8, "Helvetica-Bold")
    _p(c, inch, 1.1 * inch, "Requested delivery date: 09/26/2025. Confirm by return email.", 8)
    _p(c, inch, 0.8 * inch, "Authorized by: Dana Whitfield, Director of Materials Management", 7.5)
    c.showPage()
    c.save()


# --------------------------------------------------------------------------- #
# 2. fax: cover sheet + rotated page + continuation + terms
# --------------------------------------------------------------------------- #
def fax_multipage(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER

    # cover
    _p(c, inch, h - 1.0 * inch, "FAX COVER SHEET", 16, "Helvetica-Bold")
    lines = [
        "TO:   Chronik Medical Supply — Order Entry",
        "FAX:  (614) 555-0182",
        "FROM: Lakeview Health Partners — Purchasing",
        "DATE: 09/15/2025     PAGES: 4 (including cover)",
        "RE:   Purchase Order LV-2025-0912-08",
        "",
        "Message: Please find our order attached. Rush — OR schedule Thursday.",
    ]
    y = h - 2.0 * inch
    for line in lines:
        _p(c, inch, y, line, 10)
        y -= 0.3 * inch
    c.showPage()

    # PO page — drawn upright here; samples/rasterize.py feeds it sideways into
    # the "scanner" so the sample matches what a real fax looks like.
    _p(c, inch, h - 0.9 * inch, "LAKEVIEW HEALTH PARTNERS", 13, "Helvetica-Bold")
    _p(c, inch, h - 1.1 * inch, "1800 Lakeshore Drive, Suite 500, Milwaukee, WI 53202", 8)
    _p(c, 5.2 * inch, h - 0.9 * inch, "PURCHASE ORDER  LV-2025-0912-08", 11, "Helvetica-Bold")
    _p(c, inch, h - 1.5 * inch, "SHIP TO: St. Aidan Medical Center, 77 Prospect Ave, Receiving Dock B, Milwaukee, WI 53211", 8)
    _p(c, inch, h - 1.7 * inch, "ORDER DATE: 09/15/2025     REQUIRED BY: 09/22/2025", 8)
    _p(c, inch, h - 1.9 * inch, "SHIP VIA: UPS 3rd Day — bill to Lakeview acct 6W4471 (third party billing)", 8)

    top = h - 2.4 * inch
    heads = ["QTY", "UM", "CUSTOMER PART", "DESCRIPTION", "UNIT PRICE", "EXT"]
    xs = [inch, 1.5 * inch, 2.0 * inch, 3.3 * inch, 6.0 * inch, 7.0 * inch]
    for x, hd in zip(xs, heads):
        _p(c, x, top, hd, 8, "Helvetica-Bold")
    c.line(inch, top - 4, w - inch, top - 4)
    rows = [
        ("24", "BX", "LV-GZ44", "Gauze sponge 4x4 sterile 12ply", "18.40"),
        ("6", "CS", "LV-IV22", "IV admin set 20 drop", "63.40"),
        ("150", "EA", "LV-ST12", "Suture tray, basic, disposable", "4.85"),
    ]
    y = top - 22
    for r in rows:
        for x, val in zip(xs, r):
            _p(c, x, y, val, 9)
        _p(c, 7.0 * inch, y, f"{float(r[0]) * float(r[4]):,.2f}", 9)
        y -= 2.6 * (inch / 10)
    _p(c, inch, y - 10, "continued on page 2", 7.5, "Helvetica-Oblique")
    c.showPage()

    # continuation page (page 3 of 4) with 2 more lines + a totals block
    _p(c, inch, h - 1.0 * inch, "PAGE 2 OF 2 — CONTINUATION OF PO LV-2025-0912-08", 10, "Helvetica-Bold")
    top = h - 1.6 * inch
    heads = ["QTY", "UM", "CUSTOMER PART", "DESCRIPTION", "UNIT PRICE", "EXT"]
    xs = [inch, 1.5 * inch, 2.0 * inch, 3.3 * inch, 6.0 * inch, 7.0 * inch]
    for x, hd in zip(xs, heads):
        _p(c, x, top, hd, 8, "Helvetica-Bold")
    c.line(inch, top - 4, w - inch, top - 4)
    y = top - 22
    rows = [
        ("312", "BG", "LV-CTR10", "Cotton tip applicator 6in, 1000/bg", "3.10"),
        ("18", "BX", "LV-TP110", "Surgical tape paper 1in x 10yd, 12/bx", "6.20"),
    ]
    for r in rows:
        for x, val in zip(xs, r):
            _p(c, x, y, val, 9)
        _p(c, 7.0 * inch, y, f"{float(r[0]) * float(r[4]):,.2f}", 9)
        y -= 0.26 * inch
    _p(c, 5.6 * inch, y - 24, "PO TOTAL:", 9, "Helvetica-Bold")
    _p(c, 7.0 * inch, y - 24, "4,547.25", 9, "Helvetica-Bold")
    c.showPage()

    # terms page
    _p(c, inch, h - 1.0 * inch, "TERMS AND CONDITIONS OF SALE", 12, "Helvetica-Bold")
    body = (
        "1. ACCEPTANCE. This purchase order is an offer to buy and is expressly limited to the terms "
        "herein. Any additional or different terms proposed by Seller are rejected unless accepted in "
        "writing by Buyer. 2. SHALL BE GOVERNED by the laws of the State of Wisconsin, without regard "
        "to its conflict of laws provisions. 3. LIMITATION OF LIABILITY. In no event shall either party "
        "be liable for indirect, incidental, special or consequential damages. 4. WARRANTIES. Seller "
        "warrants all goods are merchantable, fit for intended use, and free of defects. 5. INDEMNIFICATION. "
        "Seller shall indemnify Buyer against claims arising from Seller's negligence. "
    )
    text = c.beginText(inch, h - 1.4 * inch)
    text.setFont("Helvetica", 8)
    text.setLeading(11)
    _wrap = __import__("textwrap").wrap(body * 4, 100)
    text.textLines("\n".join(_wrap))
    c.drawText(text)
    c.showPage()
    c.save()


# --------------------------------------------------------------------------- #
# 3. handwritten-looking form
# --------------------------------------------------------------------------- #
def _hand_font(c: canvas.Canvas) -> str:
    try:
        from reportlab.pdfbase import pdfmetrics

        available = set(pdfmetrics.getRegisteredFontNames())
        for f in HAND_FONTS:
            if f in available:
                return f
    except Exception:
        pass
    return "Helvetica-Oblique"


def handwritten_po(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER
    f = _hand_font(c)
    _p(c, 2.1 * inch, h - 0.7 * inch, "SPECIAL ORDER FORM", 15, "Helvetica-Bold")
    _p(c, 2.35 * inch, h - 0.9 * inch, "Mercy Ridge Home Health  ·  Madison, WI", 9)
    _p(c, inch, h - 1.15 * inch, "_" * 74, 9)
    _p(c, inch, h - 1.45 * inch, "Date:", 9, "Helvetica")
    _p(c, 1.35 * inch, h - 1.47 * inch, "9/16/25", 14, f)
    _p(c, 3.5 * inch, h - 1.45 * inch, "PO #:", 9, "Helvetica")
    _p(c, 4.0 * inch, h - 1.47 * inch, "MRHH-0916", 14, f)
    _p(c, 5.6 * inch, h - 1.45 * inch, "Req. date:", 9, "Helvetica")
    _p(c, 6.6 * inch, h - 1.47 * inch, "9/19", 14, f)

    _p(c, inch, h - 1.85 * inch, "Deliver to:", 9, "Helvetica")
    _p(c, 1.7 * inch, h - 1.87 * inch, "Mercy Ridge HH, 2201 Fish Hatchery Rd, Madison WI 53713", 11, f)
    _p(c, inch, h - 2.15 * inch, "Attention:", 9, "Helvetica")
    _p(c, 1.7 * inch, h - 2.17 * inch, "Wanda — 2nd floor supply closet", 11, f)

    _p(c, inch, h - 2.6 * inch, "ITEM", 9, "Helvetica")
    _p(c, 2.4 * inch, h - 2.6 * inch, "WHAT IT IS", 9, "Helvetica")
    _p(c, 5.0 * inch, h - 2.6 * inch, "HOW MANY", 9, "Helvetica")
    _p(c, 6.3 * inch, h - 2.6 * inch, "PRICE", 9, "Helvetica")
    c.line(inch, h - 2.68 * inch, w - inch, h - 2.68 * inch)
    rows = [
        ("MRZ-118", "wound dressings, the foam ones 4x4", "4 bx", "22.00"),
        ("??", "syringes 10ml luer lock, 100/bx", "3", "14.75"),
        ("MRZ-207", "gloves med nitrile", "10 bx", "9.75"),
        ("MRZ-401", "saline 1000ml irrigation", "2 cs", "41.60"),
        ("", "back brace, lg, the velcro kind", "1 ea", "58.00"),
    ]
    y = h - 3.0 * inch
    for a, b, q, pr in rows:
        _p(c, 1.05 * inch, y, a, 12, f)
        _p(c, 2.4 * inch, y, b, 11, f)
        _p(c, 5.05 * inch, y, q, 12, f)
        _p(c, 6.35 * inch, y, pr, 12, f)
        y -= 0.42 * inch

    _p(c, 2.0 * inch, y - 0.35 * inch, "Please call me if anything is backordered — Wanda x4412", 11, f)
    _p(c, 2.0 * inch, y - 0.85 * inch, "8/16/25 W.L.", 13, f)  # deliberately odd signature line
    c.showPage()
    c.save()


# --------------------------------------------------------------------------- #
# 4. never-seen-before format, 2 pages
# --------------------------------------------------------------------------- #
def unknown_format(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=legal)
    w, h = legal
    _p(c, 0.6 * inch, h - 0.7 * inch, "CEDAR VALLEY VETERINARY GROUP", 12, "Helvetica-Bold")
    _p(c, 0.6 * inch, h - 0.9 * inch, "Purchasing Department · 515 Alder Creek Rd · Boise, ID 83702", 7.5)
    _p(c, 5.6 * inch, h - 0.65 * inch, "REQUISITION / ORDER", 11, "Helvetica-Bold")
    _p(c, 5.6 * inch, h - 0.85 * inch, "Our ref: 2025-0614-CV", 8)
    _p(c, 5.6 * inch, h - 1.0 * inch, "Date recvd: 16 SEP 2025", 8)
    _p(c, 0.6 * inch, h - 1.3 * inch, "Consigned to:", 7.5, "Helvetica-Bold")
    _p(c, 1.6 * inch, h - 1.3 * inch, "Cedar Valley Veterinary Group, c/o warehouse, 515 Alder Creek Rd, Boise, ID 83702", 7.5)
    _p(c, 0.6 * inch, h - 1.5 * inch, "Invoicing party:", 7.5, "Helvetica-Bold")
    _p(c, 1.6 * inch, h - 1.5 * inch, "Cedar Valley Veterinary Group, AP Dept, PO Box 4407, Boise, ID 83711", 7.5)
    _p(c, 0.6 * inch, h - 1.75 * inch, "Consign via: expedited — courier account # CV-778812", 7.5)
    _p(c, 0.6 * inch, h - 1.9 * inch, "Requested arrival: on or before 22-Sep-2025", 7.5)

    top = h - 2.3 * inch
    heads = ["Ref", "Product / packaging", "How supplied", "Units", "Price ea", "Amount"]
    xs = [0.6 * inch, 1.3 * inch, 4.3 * inch, 5.1 * inch, 6.0 * inch, 7.4 * inch]
    c.setFillGray(0.9)
    c.rect(0.6 * inch, top - 3, w - 1.2 * inch, 16, fill=1, stroke=0)
    c.setFillGray(0)
    for x, hd in zip(xs, heads):
        _p(c, x, top + 2, hd, 7.5, "Helvetica-Bold")
    rows = [
        ("A1", "Examination gloves, nitrile, medium, 100 per dispenser", "10 dispenser", "10", "9.75"),
        ("A2", "Examination gloves, nitrile, large, 100 per dispenser", "8 dispenser", "8", "9.75"),
        ("B4", "Iodine solution 10%, 16 oz bottle", "6 bottle", "6", "7.40"),
        ("C2", "Suture, absorbable 3-0, 36 per box", "4 box", "4", "52.10"),
    ]
    y = top - 22
    for r in rows:
        for x, val in zip(xs, r):
            _p(c, x, y, val, 8)
        _p(c, 7.4 * inch, y, f"{float(r[3]) * float(r[4]):,.2f}", 8)
        y -= 0.22 * inch
    _p(c, 6.2 * inch, y - 20, "Goods total", 8)
    _p(c, 7.4 * inch, y - 20, "1,105.30", 8)
    _p(c, 0.6 * inch, y - 50, "Page 1 of 2 — product schedule", 7)
    c.showPage()

    # page 2: no PO number at all, just delivery notes and an approval block
    _p(c, 0.6 * inch, h - 0.8 * inch, "CEDAR VALLEY VETERINARY GROUP — page 2", 10, "Helvetica-Bold")
    notes = [
        "Delivery notes:",
        "  · Deliver to rear loading door; ring bell for receiving.",
        "  · Do not leave cartons on the dock after 3:00 pm.",
        "  · Short-ship is acceptable only with prior approval from Dr. Alcott.",
        "  · Packing list must reference our ref 2025-0614-CV.",
        "",
        "Approved by:  R. Alcott DVM        Date: 16/09/2025",
        "",
        "Vendor questions: purchasing@cedarvalleyvet.example  ·  (208) 555-0134",
    ]
    y = h - 1.3 * inch
    for line in notes:
        _p(c, 0.6 * inch, y, line, 9)
        y -= 0.24 * inch
    c.showPage()
    c.save()


# --------------------------------------------------------------------------- #
def build(out_dir: Path = OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "clean_po": out_dir / "clean_po.pdf",
        "fax_multipage": out_dir / "fax_multipage.pdf",
        "handwritten_po": out_dir / "handwritten_po.pdf",
        "unknown_format": out_dir / "unknown_format.pdf",
    }
    clean_po(files["clean_po"])
    fax_multipage(files["fax_multipage"])
    handwritten_po(files["handwritten_po"])
    unknown_format(files["unknown_format"])
    return files


if __name__ == "__main__":
    for name, path in build().items():
        print(f"{name:16s} {path}  ({path.stat().st_size/1024:.0f} KB)")
