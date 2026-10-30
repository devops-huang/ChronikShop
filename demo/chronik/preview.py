"""Render a review card to PNG.

The HTML review pack is the real tool, but a PNG is what actually travels: it
gets attached to a proposal, pasted into Slack, or dropped into a slide. One
image per order, drawn with the same data as the HTML sheet.

    python -m chronik.preview      # writes out/review/preview_<order>.png
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .pdfutil import Document
from .review import _crop_for
from .schema import OrderAssessment, Severity

PAD = 26
WIDTH = 1180  # final image width in px

INK = (16, 24, 40)
MUTED = (102, 112, 133)
LINE = (234, 236, 240)
BG = (249, 250, 251)
CARD = (255, 255, 255)
SEV = {
    Severity.BLOCK: (180, 35, 24),
    Severity.REVIEW: (181, 71, 8),
    Severity.INFO: (71, 84, 103),
}
ROUTE = {
    "auto_ready": ((6, 118, 71), "READY TO IMPORT"),
    "needs_review": ((181, 71, 8), "NEEDS REVIEW"),
    "blocked": ((180, 35, 24), "BLOCKED — CANNOT IMPORT"),
}

_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/Library/Fonts",
    "C:/Windows/Fonts",
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in _FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _f(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


def _mono(size: int) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSansMono.ttf", size)


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _trim_white(img: Image.Image, pad: int = 3) -> Image.Image:
    """Crop the empty margins a page/full-page fallback leaves behind."""
    gray = img.convert("L")
    bbox = gray.point(lambda v: 0 if v > 244 else 255).getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(img.width, x1 + pad), min(img.height, y1 + pad)
    if (x1 - x0) * (y1 - y0) < 400:
        return img
    return img.crop((x0, y0, x1, y1))


def render_order_png(order: OrderAssessment, sample_dir: str | Path, out_path: str | Path, with_crops: bool = True) -> Path:
    sample_dir = Path(sample_dir)
    o = order.extraction.order
    crop_max_w = 176 if with_crops else 0
    doc = Document(sample_dir / order.source_filename)
    try:
        # ---- collect crops first, so we know the row height --------------- #
        rows = []
        for flag in sorted(order.flags, key=lambda f: list(Severity).index(f.severity)):
            crop_b64, caption = _crop_for(order, flag.field, doc) if with_crops else (None, "")
            img = None
            if crop_b64:
                import base64

                img = Image.open(io.BytesIO(base64.b64decode(crop_b64))).convert("RGB")
                img = _trim_white(img)
                ratio = min(112 / img.height, crop_max_w / img.width)
                img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)
            rows.append((flag, img, caption))
    finally:
        doc.close()

    # ---- measure ------------------------------------------------------- #
    probe = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(probe)
    f_body, f_small, f_h2 = _f(12), _f(10), _f(15, True)

    flag_cols = [80, 172, 176, 262, 104, 124]
    crop_col_w = 176 if with_crops else 0
    def row_height(flag, img) -> int:
        heights = []
        for i, text in enumerate(
            [flag.code.value, flag.field or "", flag.message, flag.extracted or "", flag.reference or ""]
        ):
            heights.append(len(_wrap(d, text, f_small, flag_cols[i] - 14)) * 15)
        if img is not None:
            heights.append(img.height + 16)
        return max(max(heights), 22) + 12

    body_h = sum(row_height(flag, img) for flag, img, _ in rows)

    table_h = 26 + body_h + (0 if rows else 40)
    lines_h = 26 + 22 * len(order.resolved_lines) + 8
    head_h = 96
    total_h = head_h + table_h + lines_h + 90

    img_canvas = Image.new("RGB", (WIDTH, total_h), BG)
    dr = ImageDraw.Draw(img_canvas)

    def T(x, y, text, font, fill=INK):
        dr.text((x, y), text, font=font, fill=fill)

    # ---- header -------------------------------------------------------- #
    y = PAD
    T(PAD, y, "Purchase-order agent — review card", _f(15, True))
    y += 30
    route_color, route_label = ROUTE[order.route]
    T(PAD, y, o.po_number or "NO PO NUMBER", _f(26, True))
    tw = dr.textlength(o.po_number or "NO PO NUMBER", font=_f(26, True))
    dr.rounded_rectangle([PAD + tw + 16, y + 2, PAD + tw + 16 + 210, y + 30], 14, fill=route_color)
    T(PAD + tw + 30, y + 8, route_label, _f(11, True), (255, 255, 255))
    y += 42
    meta = (
        f"{order.source_filename}  ·  {order.customer_name or 'unknown customer'}"
        f"  ·  ship-to {order.ship_to_id or '—'}  ·  {len(order.resolved_lines)} lines"
        f"  ·  confidence {order.order_confidence:.0%}"
        f"  ·  model {order.extraction.model}"
    )
    T(PAD, y, meta, _f(11), MUTED)
    y += 26
    dr.line([PAD, y, WIDTH - PAD, y], fill=LINE)
    y += 18

    # ---- flags table --------------------------------------------------- #
    T(PAD, y, "FLAGS", _f(11, True), MUTED)
    y += 24
    dr.rounded_rectangle([PAD, y, WIDTH - PAD, y + table_h + 20], 10, fill=CARD, outline=LINE)
    y += 12
    heads = ["SEVERITY", "CODE", "FIELD", "WHY", "EXTRACTED", "REFERENCE"]
    x = PAD + 14
    for head, w in zip(heads, flag_cols):
        T(x, y, head, _f(9, True), MUTED)
        x += w
    if with_crops:
        T(x, y, "SOURCE ON THE PAGE", _f(9, True), MUTED)
    y += 20
    dr.line([PAD + 14, y, WIDTH - PAD - 14, y], fill=LINE)
    y += 8

    if not rows:
        T(PAD + 14, y + 8, "No flags — every field reconciled against reference data and arithmetic.", _f(12), (6, 118, 71))
    for flag, img, caption in rows:
        rh = row_height(flag, img)
        x = PAD + 14
        color = SEV[flag.severity]
        pill_w = 78
        dr.rounded_rectangle([x, y + 1, x + pill_w, y + 19], 9, fill=color)
        T(x + 10, y + 4, flag.severity.value.upper(), _f(9, True), (255, 255, 255))
        x += flag_cols[0]
        for i, text in enumerate([flag.code.value, flag.field or ""]):
            lines = _wrap(d, text, _mono(10) if i == 0 else _f(10), flag_cols[i + 1] - 16)
            for j, ln in enumerate(lines):
                T(x, y + 3 + j * 14, ln, _mono(10) if i == 0 else _f(10), INK)
            x += flag_cols[i + 1]
        for i, text in enumerate([flag.message, flag.extracted or "", flag.reference or ""]):
            lines = _wrap(d, text, _f(10), flag_cols[i + 3] - 16)
            for j, ln in enumerate(lines):
                T(x, y + 3 + j * 14, ln, _f(10), INK if i == 0 else MUTED)
            x += flag_cols[i + 3]
        if img is not None:
            img_canvas.paste(img, (x, y))
            T(x, y + img.height + 1, caption, _f(9), MUTED)
        y += rh
        dr.line([PAD + 14, y - 5, WIDTH - PAD - 14, y - 5], fill=(245, 246, 248))

    y += 14
    T(PAD, y, "RESOLVED LINES", _f(11, True), MUTED)
    y += 24
    dr.rounded_rectangle([PAD, y, WIDTH - PAD, y + lines_h], 10, fill=CARD, outline=LINE)
    y += 12
    lheads = [("#", 34), ("CUST ITEM", 110), ("ERP ITEM", 110), ("DESCRIPTION AS PRINTED", 430), ("QTY", 56), ("UOM", 96), ("PRICE", 74), ("ERP PRICE", 82), ("MATCH", 100)]
    x = PAD + 14
    for head, w in lheads:
        T(x, y, head, _f(9, True), MUTED)
        x += w
    y += 18
    dr.line([PAD + 14, y, WIDTH - PAD - 14, y], fill=LINE)
    y += 6
    for rl in order.resolved_lines:
        e = rl.extracted
        x = PAD + 14
        cells = [
            str(rl.line_no),
            e.customer_item_no or "—",
            rl.sku or "—",
            (e.description or "")[:62],
            str(e.qty) if e.qty is not None else "",
            f"{e.uom or '?'} → {rl.uom or '?'}",
            f"{e.unit_price:.2f}" if e.unit_price is not None else "",
            f"{rl.erp_price:.2f}" if rl.erp_price is not None else "",
            rl.match_method,
        ]
        for (head, w), val in zip(lheads, cells):
            T(x, y, val, _mono(10) if head in ("CUST ITEM", "ERP ITEM") else _f(10), INK if head != "MATCH" else MUTED)
            x += w
        y += 20

    y += 12
    T(PAD, y, "Synthetic sample data. Every flag points at the exact printed line it came from.", _f(9), MUTED)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img_canvas.save(out_path, optimize=True)
    return out_path


def render_all(results, sample_dir, out_dir, with_crops: bool = True) -> list[Path]:
    paths = []
    for r in results:
        p = Path(out_dir) / f"preview_{r.assessment.order_id}.png"
        paths.append(render_order_png(r.assessment, sample_dir, p, with_crops))
    return paths


if __name__ == "__main__":
    from .cli import ROOT
    from .matching import ReferenceData
    from .pipeline import Settings, default_extractor, run_batch

    out = ROOT / "out"
    results = run_batch(
        ROOT / "samples",
        ROOT / "samples" / "mail_manifest.json",
        ReferenceData(ROOT / "data" / "erp"),
        default_extractor(ROOT / "fixtures"),
        Settings.load(ROOT / "config" / "settings.json"),
        out,
    )
    for p in render_all(results, ROOT / "samples", out / "review"):
        print(p)
