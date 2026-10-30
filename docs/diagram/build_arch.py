"""Generate the architecture diagram as SVG (and a PNG preview).

Hand-drawn-in-code so the diagram can be regenerated whenever the design moves —
a diagram that lives as a binary export is a diagram nobody updates.

    python docs/diagram/build_arch.py            # writes architecture.svg
    python docs/diagram/build_arch.py --png      # also writes architecture.png
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
W, H = 1680, 930

INK = "#0f172a"
MUTED = "#64748b"
LINE = "#cbd5e1"
CARD = "#ffffff"
BG = "#f6f8fb"

BLUE = "#1d4ed8"
BLUE_BG = "#eef4ff"
BLUE_LINE = "#c7d7fe"
GREEN = "#067647"
GREEN_BG = "#ecfdf3"
GREEN_LINE = "#abefc6"
AMBER = "#b54708"
AMBER_BG = "#fffaeb"
AMBER_LINE = "#fedf89"
SLATE_BG = "#f2f4f7"
GREY = "#475569"
RED = "#b42318"

parts: list[str] = []


def add(s: str) -> None:
    parts.append(s)


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, t, size=13, fill=INK, weight="400", anchor="start", family="Inter, Segoe UI, Helvetica, Arial, sans-serif", ls="0"):
    add(
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{ls}">{esc(t)}</text>'
    )


def box(x, y, w, h, fill=CARD, stroke=LINE, r=12, dash=None, sw=1.4, opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"{d} opacity="{opacity}"/>'
    )


def arrow(x1, y1, x2, y2, color=GREY, sw=1.8, dash=None, label=None, lx=None, ly=None, curve=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    if curve:
        cx, cy = curve
        path = f"M{x1},{y1} Q{cx},{cy} {x2},{y2}"
        add(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{sw}"{d} marker-end="url(#arrow-{color.strip("#")})"/>')
    else:
        add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{d} marker-end="url(#arrow-{color.strip("#")})"/>')
    if label:
        text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 7,
             label, 11, MUTED, anchor="middle")


def pill(x, y, label, fill, fg="#fff", size=10.5, padx=9, h=19):
    w = len(label) * size * 0.62 + padx * 2
    add(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{h}" rx="{h/2}" fill="{fill}"/>')
    text(x + w / 2, y + h / 2 + size * 0.36, label, size, fg, "600", "middle")
    return w


# --------------------------------------------------------------------------- #
# canvas + defs
# --------------------------------------------------------------------------- #
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Purchase-order intake agent architecture">')
add("<defs>")
for color in (GREY, BLUE, GREEN, AMBER, "#98a2b3"):
    add(
        f'<marker id="arrow-{color.strip("#")}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
    )
add(
    '<linearGradient id="hdr" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="{BLUE_BG}"/></linearGradient>'
)
add("</defs>")
add(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

# title
text(64, 62, "Purchase-order intake agent", 25, INK, "700")
text(64, 90, "Template-free extraction, everything inside the client's own Azure tenant", 13.5, MUTED)
x = W - 64
for lbl, col in (("No third-party SaaS", RED), ("No per-page fees", RED), ("Code owned day one", GREEN)):
    wpx = len(lbl) * 10.5 * 0.62 + 20
    x -= wpx + 8
    add(f'<rect x="{x:.0f}" y="44" width="{wpx:.0f}" height="26" rx="13" fill="#fff" stroke="{LINE}"/>')
    text(x + wpx / 2, 61, lbl, 10.5, col, "600", "middle")
text(W - 64, 92, "Client Azure subscription · gpt-4.1 vision · ~$0.02–0.05 per order", 11.5, MUTED, anchor="end")

# --------------------------------------------------------------------------- #
# lane 1 — intake
# --------------------------------------------------------------------------- #
LANE_Y = 128
box(48, LANE_Y, 380, 214, CARD, LINE)
text(72, LANE_Y + 30, "1 · INTAKE", 10.5, MUTED, "700", ls="0.14em")

box(70, LANE_Y + 46, 336, 62, SLATE_BG, LINE, r=9)
text(86, LANE_Y + 70, "Outlook shared mailbox · Front · fax", 12.5, INK, "600")
text(86, LANE_Y + 90, "new message with PDF attachments", 11.5, MUTED)

arrow(238, LANE_Y + 108, 238, LANE_Y + 136)

box(70, LANE_Y + 136, 336, 58, AMBER_BG, AMBER_LINE, r=9)
text(86, LANE_Y + 158, "Power Automate (thin trigger)", 12.5, INK, "600")
text(86, LANE_Y + 177, "filters non-PDF · stores · enqueues — no business logic", 10.8, MUTED)

# --------------------------------------------------------------------------- #
# lane 2 — storage / queue
# --------------------------------------------------------------------------- #
box(468, LANE_Y, 250, 214, CARD, LINE)
text(492, LANE_Y + 30, "2 · BUFFER", 10.5, MUTED, "700", ls="0.14em")
box(490, LANE_Y + 48, 206, 62, SLATE_BG, LINE, r=9)
text(504, LANE_Y + 72, "Blob: original PDF", 12, INK, "600")
text(504, LANE_Y + 92, "sha256 · never mutated", 11, MUTED)
box(490, LANE_Y + 124, 206, 66, SLATE_BG, LINE, r=9)
text(504, LANE_Y + 148, "Storage Queue", 12, INK, "600")
text(504, LANE_Y + 168, "retry · dead-letter · idempotent", 11, MUTED)

# --------------------------------------------------------------------------- #
# lane 3 — worker
# --------------------------------------------------------------------------- #
WX, WY, WW, WH = 758, LANE_Y, 620, 500
add(f'<rect x="{WX}" y="{WY}" width="{WW}" height="{WH}" rx="16" fill="{BLUE_BG}" stroke="{BLUE_LINE}" stroke-width="1.6"/>')
text(WX + 24, WY + 30, "3 · WORKER  ·  Azure Container App (our code, your subscription)", 10.5, BLUE, "700", ls="0.12em")

stage_w, stage_h = 178, 84
cols = [WX + 22, WX + 222, WX + 422]
y1 = WY + 50
y2 = WY + 198

stages = [
    (cols[0], y1, "① Triage", ["page roles by rules", "cover / terms / blank", "never reach the model"], GREEN_BG, GREEN_LINE),
    (cols[1], y1, "② Render", ["PO pages only, 200 dpi", "rotation correction", "text layer when present"], GREEN_BG, GREEN_LINE),
    (cols[2], y1, "③ Extract", ["Azure OpenAI gpt-4.1", "vision + strict JSON schema", "cites page + quote"], BLUE_BG, BLUE_LINE),
    (cols[0], y2, "④ Match", ["customer · ship-to", "part crosswalk · UOM", "price list"], BLUE_BG, BLUE_LINE),
    (cols[1], y2, "⑤ Validate + route", ["arithmetic · evidence", "quality ceiling", "auto / review / block"], AMBER_BG, AMBER_LINE),
    (cols[2], y2, "⑥ Emit", ["one CSV per order", "atomic write", "audit JSON + crops"], AMBER_BG, AMBER_LINE),
]
for sx, sy, title, lines, fill, stroke in stages:
    box(sx, sy, stage_w, stage_h, fill, stroke, r=10)
    text(sx + 14, sy + 26, title, 13, INK, "700")
    for i, ln in enumerate(lines):
        text(sx + 14, sy + 46 + i * 15, ln, 10.8, MUTED)

# arrows between stages
arrow(cols[0] + stage_w + 3, y1 + stage_h / 2, cols[1] - 3, y1 + stage_h / 2, BLUE, 1.6)
arrow(cols[1] + stage_w + 3, y1 + stage_h / 2, cols[2] - 3, y1 + stage_h / 2, BLUE, 1.6)
add(f'<path d="M{cols[2] + stage_w / 2},{y1 + stage_h + 2} V{y2 - 26} H{cols[0] + stage_w / 2} V{y2 - 2}" fill="none" stroke="{BLUE}" stroke-width="1.6" marker-end="url(#arrow-1d4ed8)"/>')
arrow(cols[0] + stage_w + 3, y2 + stage_h / 2, cols[1] - 3, y2 + stage_h / 2, BLUE, 1.6)
arrow(cols[1] + stage_w + 3, y2 + stage_h / 2, cols[2] - 3, y2 + stage_h / 2, BLUE, 1.6)

# evidence ladder panel
lx, ly, lw = WX + 22, y2 + stage_h + 22, WW - 44
box(lx, ly, lw, 138, "#ffffff", BLUE_LINE, r=10)
text(lx + 16, ly + 26, "Confidence is computed, not claimed  —  strongest signal first", 11.5, INK, "700")
ladder = [
    ("1  arithmetic identity", "qty × price = extended · catches a missing page", 0.99),
    ("2  reference data", "crosswalk · contract price · UOM list", 0.95),
    ("3  evidence re-check", "quote must exist on the cited page", 0.85),
    ("4  page quality ceiling", "scanned ≤ 0.93 · handwritten ≤ 0.85", 0.6),
    ("5  model self-report", "weakest — can only lower the score", 0.35),
]
for i, (name, desc, bar) in enumerate(ladder):
    yy = ly + 50 + i * 18
    text(lx + 16, yy, name, 10.5, INK, "600")
    text(lx + 186, yy, desc, 10.2, MUTED)
    add(f'<rect x="{lx + lw - 92}" y="{yy - 9}" width="76" height="6" rx="3" fill="#e2e8f0"/>')
    colr = GREEN if bar > 0.8 else AMBER if bar > 0.5 else RED
    add(f'<rect x="{lx + lw - 92}" y="{yy - 9}" width="{76 * bar:.0f}" height="6" rx="3" fill="{colr}"/>')

# --------------------------------------------------------------------------- #
# lane 4 — outputs
# --------------------------------------------------------------------------- #
OX = 1418
box(OX, LANE_Y, 214, 214, CARD, GREEN_LINE)
text(OX + 24, LANE_Y + 30, "4 · OUTPUT", 10.5, MUTED, "700", ls="0.14em")
box(OX + 16, LANE_Y + 46, 182, 66, GREEN_BG, GREEN_LINE, r=9)
text(OX + 30, LANE_Y + 70, "ERP drop folder", 12, INK, "600")
text(OX + 30, LANE_Y + 89, "one CSV per order", 11, MUTED)
text(OX + 30, LANE_Y + 104, "imported by your partner", 10.2, MUTED)
box(OX + 16, LANE_Y + 122, 182, 68, AMBER_BG, AMBER_LINE, r=9)
text(OX + 30, LANE_Y + 146, "Review pack", 12, INK, "600")
text(OX + 30, LANE_Y + 165, "Teams card + crops of", 10.8, MUTED)
text(OX + 30, LANE_Y + 180, "the exact printed line", 10.8, MUTED)

box(OX, LANE_Y + 234, 214, 246, CARD, LINE)
text(OX + 24, LANE_Y + 262, "5 · REVIEW LOOP", 10.5, MUTED, "700", ls="0.14em")
for i, (t, d) in enumerate([
    ("Rep fixes a field", "review sheet or Teams card"),
    ("Re-emit CSV", "attempt + 1, old archived"),
    ("Sample audit", "spot-check auto-ready orders"),
    ("Metrics", "auto-rate · flags · $/order"),
]):
    yy = LANE_Y + 286 + i * 46
    add(f'<circle cx="{OX + 28}" cy="{yy - 4}" r="9" fill="{SLATE_BG}" stroke="{LINE}"/>')
    text(OX + 28, yy, str(i + 1), 10, GREY, "700", "middle")
    text(OX + 46, yy - 6, t, 11.5, INK, "600")
    text(OX + 46, yy + 10, d, 10.2, MUTED)

# --------------------------------------------------------------------------- #
# lane 5 — platform services
# --------------------------------------------------------------------------- #
PY_ = 664
box(48, PY_, 654, 132, CARD, LINE)
text(72, PY_ + 28, "6 · REFERENCE DATA  (nightly sync, client-owned CSVs)", 10.5, MUTED, "700", ls="0.12em")
for i, (t, d) in enumerate([
    ("customers + aliases", "email domains, printed-name aliases"),
    ("ship-to addresses", "scoped per customer — never global fuzzy"),
    ("item crosswalk", "customer part · legacy · UPC → ERP SKU"),
    ("price · UOM list", "contract price + canonical units"),
]):
    xx = 72 + (i % 2) * 322
    yy = PY_ + 54 + (i // 2) * 54
    text(xx, yy, "• " + t, 11.2, INK, "600")
    text(xx + 12, yy + 15, d, 10.2, MUTED)

box(738, PY_, 700, 132, CARD, LINE)
text(762, PY_ + 28, "7 · PLATFORM  (all in your tenant, no long-lived secrets)", 10.5, MUTED, "700", ls="0.12em")
for i, (t, d) in enumerate([
    ("Managed Identity", "no API keys on disk; Key Vault for the rest"),
    ("Application Insights", "per-stage traces, cost per document"),
    ("Blob versioning · audit log", "original PDF hash + prompt version kept"),
    ("Bicep / azd deploy", "whole stack reproducible in one command"),
]):
    xx = 762 + (i % 2) * 340
    yy = PY_ + 54 + (i // 2) * 54
    text(xx, yy, "• " + t, 11.2, INK, "600")
    text(xx + 12, yy + 15, d, 10.2, MUTED)

# --------------------------------------------------------------------------- #
# flows between lanes
# --------------------------------------------------------------------------- #
arrow(418, LANE_Y + 165, 466, LANE_Y + 165, GREY, 1.8, label="attachment", lx=442, ly=LANE_Y + 150)
add(f'<path d="M718,{LANE_Y + 157} H736 V{LANE_Y + 110} H756" fill="none" stroke="{GREY}" stroke-width="1.8" marker-end="url(#arrow-475569)"/>')
text(737, LANE_Y + 148, "job", 11, MUTED)

add(f'<path d="M1378,{LANE_Y + 80} H1400 V{LANE_Y + 80}" fill="none" stroke="{GREEN}" stroke-width="1.8"/>')
arrow(1378, LANE_Y + 80, OX - 2, LANE_Y + 80, GREEN, 1.8)
arrow(1378, LANE_Y + 156, OX - 2, LANE_Y + 156, AMBER, 1.8)
text(1386, LANE_Y + 66, "CSV", 10.2, GREEN, "600")
text(1386, LANE_Y + 142, "flags", 10.2, AMBER, "600")

# review loop back into emit
add(
    f'<path d="M{1418},{LANE_Y + 200} H1398 V{y2 + stage_h / 2} H{cols[2] + stage_w + 2}" '
    f'fill="none" stroke="{AMBER}" stroke-width="1.6" stroke-dasharray="5 4" marker-end="url(#arrow-b54708)"/>'
)


# reference data feeds match stage
add(
    f'<path d="M470,{PY_} V{LANE_Y + WH + 18} H{cols[0] + 40} V{y2 + stage_h + 2}" '
    f'fill="none" stroke="#98a2b3" stroke-width="1.5" stroke-dasharray="5 4" marker-end="url(#arrow-98a2b3)"/>'
)
text(482, PY_ - 12, "reference data feeds ④ Match", 10.2, MUTED, "600")

# footnote
text(64, H - 44, "Cover and terms pages are never sent to the model, so a 4-page fax costs two vision calls, not four.", 11.6, MUTED)
text(64, H - 24, "Everything above runs in the client's Azure subscription under the client's identity; the only external dependency is the model endpoint they own.", 11.6, MUTED)
add("</svg>")

svg = "\n".join(parts)
(OUT / "architecture.svg").write_text(svg, encoding="utf-8")
print(f"wrote {OUT / 'architecture.svg'}  ({len(svg)/1024:.0f} KB)")

if "--png" in sys.argv:
    try:
        import pymupdf

        doc = pymupdf.open(str(OUT / "architecture.svg"))
        page = doc[0]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6))
        pix.save(str(OUT / "architecture.png"))
        print(f"wrote {OUT / 'architecture.png'}  ({pix.width}x{pix.height})")
    except Exception as exc:  # pragma: no cover
        print("PNG export failed:", exc)
