"""Render a review card to PNG.

The HTML review pack is the real tool, but a PNG is what actually travels: it
gets attached to a proposal, pasted into Slack, or dropped into a slide. One
image per order, same data as the HTML sheet.

    python -m chronik.preview                 # out/review/preview_<order>.png (bilingual)
    python -m chronik.preview --lang en       # English labels only

Chinese labels need a CJK font (Noto Sans CJK / PingFang / Microsoft YaHei).
If none is found the card silently falls back to English labels instead of
drawing empty boxes.
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .i18n import LABELS
from .i18n import lang as active_lang
from .i18n import t
from .pdfutil import Document
from .review import _crop_for
from .schema import OrderAssessment, Severity

PAD = 26
WIDTH = 1320

INK = (16, 24, 40)
MUTED = (102, 112, 133)
LINE = (234, 236, 240)
BG = (249, 250, 251)
CARD = (255, 255, 255)
DELIM = " · "

SEV = {
    Severity.BLOCK: (180, 35, 24),
    Severity.REVIEW: (181, 71, 8),
    Severity.INFO: (71, 84, 103),
}
ROUTE_COLOR = {
    "auto_ready": (6, 118, 71),
    "needs_review": (181, 71, 8),
    "blocked": (180, 35, 24),
}

# --------------------------------------------------------------------------- #
# fonts: one face must cover Latin + 中文
# --------------------------------------------------------------------------- #
_FONT_DIRS = [
    str(Path.home() / ".fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/opentype/noto",
    "/usr/local/share/fonts",
    "/Library/Fonts",
    "C:/Windows/Fonts",
]

_CJK = {
    False: ["NotoSansCJKsc-Regular.otf", "NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf",
            "SourceHanSansSC-Regular.otf", "msyh.ttc", "simhei.ttf", "PingFang.ttc"],
    True: ["NotoSansCJKsc-Bold.otf", "NotoSansCJK-Bold.ttc", "NotoSansSC-Bold.otf",
           "SourceHanSansSC-Bold.otf", "msyhbd.ttc", "simhei.ttf", "PingFang.ttc"],
}
_LATIN = {False: ["DejaVuSans.ttf"], True: ["DejaVuSans-Bold.ttf"]}
_MONO = ["DejaVuSansMono.ttf", "NotoSansMonoCJKsc-Regular.otf"]


def _find(names: list[str]) -> Path | None:
    for d in _FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return p
    return None


def _load(names: list[str], size: int):
    p = _find(names)
    if p:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            pass
    return ImageFont.load_default()


def has_cjk_font() -> bool:
    return _find(_CJK[False]) is not None


def _f(size: int, bold: bool = False):
    """UI text: prefer a CJK face (it carries Latin too), fall back to DejaVu.

    A missing *bold* CJK face must fall back to the regular CJK face before
    DejaVu, otherwise Chinese turns into tofu (empty boxes) on the card.
    """
    if has_cjk_font():
        return _load(_CJK[bold] + _CJK[False], size)
    return _load(_LATIN[bold], size)


def _mono(size: int):
    return _load(_MONO + _LATIN[False], size)


def _effective_lang() -> str:
    mode = active_lang()
    if mode in ("both", "zh") and not has_cjk_font():
        return "en"  # never draw tofu boxes on a card we might send to a client
    return mode


# --------------------------------------------------------------------------- #
# drawing helpers
# --------------------------------------------------------------------------- #
def _wrap(draw, text: str, font, max_w: float) -> list[str]:
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


class Card:
    """Small drawing surface: tracks the cursor so nothing overlaps by accident."""

    def __init__(self, height: int):
        self.img = Image.new("RGB", (WIDTH, height), BG)
        self.d = ImageDraw.Draw(self.img)

    def text(self, x, y, s, font, fill=INK, anchor="la"):
        self.d.text((x, y), s, font=font, fill=fill, anchor=anchor)

    def head(self, x, y, label: str, size: int = 9) -> None:
        """Bilingual column head: English on top, 中文 underneath (when both)."""
        en, zh = (label.split(DELIM, 1) + [""])[:2] if DELIM in label else (label, "")
        self.text(x, y, en.upper(), _f(size, True), MUTED)
        if zh:
            self.text(x, y + size + 3, zh, _f(size - 0.5), MUTED)


# --------------------------------------------------------------------------- #
# renderer
# --------------------------------------------------------------------------- #
def render_order_png(
    order: OrderAssessment,
    sample_dir: str | Path,
    out_path: str | Path,
    with_crops: bool = True,
) -> Path:
    sample_dir = Path(sample_dir)
    o = order.extraction.order
    crop_max_w = 188 if with_crops else 0

    # ---- crops first: they drive row heights -------------------------- #
    doc = Document(sample_dir / order.source_filename)
    try:
        rows = []
        for flag in sorted(order.flags, key=lambda f: list(Severity).index(f.severity)):
            crop_b64, caption = _crop_for(order, flag.field, doc) if with_crops else (None, "")
            img = None
            if crop_b64:
                img = Image.open(io.BytesIO(base64.b64decode(crop_b64))).convert("RGB")
                img = _trim_white(img)
                ratio = min(112 / img.height, crop_max_w / img.width, 1.0)
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS
                )
            rows.append((flag, img, caption))
    finally:
        doc.close()

    # ---- measurement -------------------------------------------------- #
    probe = Card(10)
    d = probe.d
    f_small = _f(10)
    flag_cols = [84, 186, 190, 296, 108, 128]
    line_cols = [40, 118, 116, 436, 62, 104, 92, 92, 118]

    def row_height(flag, img) -> int:
        heights = []
        for i, text in enumerate(
            [flag.code.value, flag.field or "", flag.message, flag.extracted or "", flag.reference or ""]
        ):
            heights.append(len(_wrap(d, text, f_small, flag_cols[i] - 14)) * 15)
        if img is not None:
            heights.append(img.height + 14)
        return max(max(heights), 22) + 12

    flags_head_h = 34
    body_h = sum(row_height(flag, img) for flag, img, _ in rows)
    table_h = flags_head_h + body_h + (24 if not rows else 0) + 16
    lines_h = 30 + 20 * len(order.resolved_lines) + 48
    head_h = 128
    total_h = head_h + table_h + lines_h + 92

    card = Card(total_h)
    dr = card.d

    # ---- header ------------------------------------------------------- #
    y = PAD
    title_en, title_zh = LABELS["title"]
    card.text(PAD, y, title_en, _f(15, True))
    if _effective_lang() == "both":
        card.text(PAD, y + 19, title_zh, _f(11.5), MUTED)
        y += 20
    y += 30
    po = o.po_number or "NO PO NUMBER"
    card.text(PAD, y, po, _f(26, True))
    tw = dr.textlength(po, font=_f(26, True))
    route_label = t(order.route).upper()
    pill_w = int(dr.textlength(route_label, font=_f(11, True))) + 34
    dr.rounded_rectangle([PAD + tw + 16, y + 2, PAD + tw + 16 + pill_w, y + 30], 14,
                         fill=ROUTE_COLOR[order.route])
    card.text(PAD + tw + 30, y + 8, route_label, _f(11, True), (255, 255, 255))
    y += 42
    meta = (
        f"{order.source_filename}  ·  {order.customer_name or 'unknown customer'}"
        f"  ·  {t('ship_to')} {order.ship_to_id or '—'}"
        f"  ·  {len(order.resolved_lines)} {t('lines')}"
        f"  ·  {t('confidence')} {order.order_confidence:.0%}"
        f"  ·  {t('model')} {order.extraction.model}"
    )
    card.text(PAD, y, meta, _f(10.5), MUTED)
    y += 26
    dr.line([PAD, y, WIDTH - PAD, y], fill=LINE)
    y += 18

    # ---- flags table --------------------------------------------------- #
    card.text(PAD, y, t("flags").upper(), _f(11, True), MUTED)
    y += 24
    dr.rounded_rectangle([PAD, y, WIDTH - PAD, y + table_h], 10, fill=CARD, outline=LINE)
    y += 12
    hx = PAD + 14
    for label, w in zip(
        [t("severity"), t("code"), t("field"), t("why"), t("extracted"), t("reference")], flag_cols
    ):
        card.head(hx, y, label)
        hx += w
    if with_crops:
        card.head(hx, y, t("source"))
    y += flags_head_h
    dr.line([PAD + 14, y - 12, WIDTH - PAD - 14, y - 12], fill=LINE)

    if not rows:
        card.text(PAD + 14, y + 6, t("no_flags"), _f(11), (6, 118, 71))
        y += 26
    for flag, img, caption in rows:
        rh = row_height(flag, img)
        x = PAD + 14
        color = SEV[flag.severity]
        dr.rounded_rectangle([x, y + 1, x + 74, y + 19], 9, fill=color)
        card.text(x + 10, y + 4, flag.severity.value.upper(), _f(9, True), (255, 255, 255))
        x += flag_cols[0]
        for i, text in enumerate([flag.code.value, flag.field or ""]):
            font = _mono(10) if i == 0 else _f(10)
            for j, ln in enumerate(_wrap(d, text, font, flag_cols[i + 1] - 14)):
                card.text(x, y + 3 + j * 14, ln, font, INK)
            x += flag_cols[i + 1]
        for i, text in enumerate([flag.message, flag.extracted or "", flag.reference or ""]):
            for j, ln in enumerate(_wrap(d, text, _f(10), flag_cols[i + 3] - 14)):
                card.text(x, y + 3 + j * 14, ln, _f(10), INK if i == 0 else MUTED)
            x += flag_cols[i + 3]
        if img is not None:
            card.img.paste(img, (x, y))
            card.text(x, y + img.height + 1, caption, _f(9), MUTED)
        y += rh
        dr.line([PAD + 14, y - 5, WIDTH - PAD - 14, y - 5], fill=(245, 246, 248))

    y += 14

    # ---- resolved lines ------------------------------------------------ #
    card.text(PAD, y, t("resolved_lines").upper(), _f(11, True), MUTED)
    y += 24
    dr.rounded_rectangle([PAD, y, WIDTH - PAD, y + lines_h], 10, fill=CARD, outline=LINE)
    y += 12
    lx = PAD + 14
    heads = [t("line_no"), t("cust_item"), t("erp_item"), t("description"), t("qty"),
             t("uom"), t("printed_price"), t("erp_price"), t("match")]
    for label, w in zip(heads, line_cols):
        card.head(lx, y, label)
        lx += w
    y += 30
    dr.line([PAD + 14, y - 12, WIDTH - PAD - 14, y - 12], fill=LINE)
    for rl in order.resolved_lines:
        e = rl.extracted
        cells = [
            str(rl.line_no),
            e.customer_item_no or "—",
            rl.sku or "—",
            (e.description or "")[:64],
            str(e.qty) if e.qty is not None else "",
            f"{e.uom or '?'} → {rl.uom or '?'}",
            f"{e.unit_price:.2f}" if e.unit_price is not None else "",
            f"{rl.erp_price:.2f}" if rl.erp_price is not None else "",
            rl.match_method,
        ]
        x = PAD + 14
        for (label, w), val in zip(zip(heads, line_cols), cells):
            mono = label in (heads[1], heads[2])
            card.text(x, y, val, _mono(10) if mono else _f(10), MUTED if label == heads[8] else INK)
            x += w
        y += 20

    y += 12
    card.text(PAD, y, t("subtitle"), _f(9), MUTED)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    card.img.save(out_path, optimize=True)
    return out_path


def render_all(results, sample_dir, out_dir, with_crops: bool = True) -> list[Path]:
    return [
        render_order_png(r.assessment, sample_dir, Path(out_dir) / f"preview_{r.assessment.order_id}.png", with_crops)
        for r in results
    ]


def main(argv: list[str] | None = None) -> int:
    import os

    from .cli import ROOT
    from .matching import ReferenceData
    from .pipeline import Settings, default_extractor, run_batch

    argv = argv if argv is not None else sys.argv[1:]
    if "--lang" in argv:
        os.environ["CHRONIK_LANG"] = argv[argv.index("--lang") + 1]

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
