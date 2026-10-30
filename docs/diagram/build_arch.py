"""Generate the architecture diagram (bilingual by default) as SVG + PNG.

Diagram-as-code, with a tiny layout engine: every card measures its content
first and then sizes itself, so adding a language or a sentence cannot make the
text overlap. That matters here because we ship three variants of the same
design (EN + 中文 for internal review, EN only for the client).

    python docs/diagram/build_arch.py                 # bilingual → architecture.{svg,png}
    python docs/diagram/build_arch.py --lang en       # → architecture_en.{svg,png}
    python docs/diagram/build_arch.py --lang zh       # → architecture_zh.{svg,png}
    python docs/diagram/build_arch.py --all           # all three

Chinese text needs a CJK font installed (Noto Sans CJK / PingFang / YaHei).
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #
INK = "#0f172a"
MUTED = "#64748b"
LINE = "#cbd5e1"
CARD = "#ffffff"
BG = "#f6f8fb"
ZH_C = "#5b6675"

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

EN_FONT = "Inter, Segoe UI, Helvetica, Arial, sans-serif"
ZH_FONT = "'Noto Sans CJK SC', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'Source Han Sans SC', sans-serif"

# role -> (en size, zh size, en weight, colour)
ROLES = {
    "h1": (24, 15, "700", INK),
    "sub": (12.5, 11, "400", MUTED),
    "eyebrow": (10.5, 10, "700", MUTED),
    "title": (12.5, 10.5, "700", INK),
    "body": (10.6, 10, "400", MUTED),
    "micro": (10, 9.4, "400", MUTED),
    "strong": (11.2, 10, "600", INK),
}

parts: list[str] = []
LANG = "both"


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text(x, y, s, size, fill, weight, anchor, family, ls="0"):
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{ls}">{esc(s)}</text>'
    )


def box(x, y, w, h, fill=CARD, stroke=LINE, r=12, dash=None, sw=1.4):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" ry="{r}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
    )


def arrow(x1, y1, x2, y2, color=GREY, sw=1.8, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
        f'stroke-width="{sw}"{d} marker-end="url(#arrow-{color.strip("#")})"/>'
    )


def path(d, color=GREY, sw=1.6, dash=None, marker=True):
    m = f' marker-end="url(#arrow-{color.strip("#")})"' if marker else ""
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{ds}{m}/>')


# --------------------------------------------------------------------------- #
# layout engine: a "para" is (role, en, zh)
# --------------------------------------------------------------------------- #
def line_h(role: str) -> float:
    en, zh, _, _ = ROLES[role]
    if LANG == "both":
        return en * 1.22 + zh * 1.28 + 2
    if LANG == "zh":
        return zh * 1.45
    return en * 1.42


def measure(paras: list[tuple], gap: float = 4) -> float:
    return sum(line_h(p[0]) for p in paras) + gap * max(len(paras) - 1, 0)


def draw_paras(x: float, y: float, paras: list[tuple], gap: float = 4, align="start") -> float:
    """Draw stacked (role, en, zh) paragraphs; returns the bottom y."""
    cy = y
    for i, (role, en, zh) in enumerate(paras):
        en_size, zh_size, weight, color = ROLES[role]
        if LANG == "zh":
            _text(x, cy + zh_size, zh, zh_size, color, weight, align, ZH_FONT)
            cy += line_h(role)
        elif LANG == "en":
            _text(x, cy + en_size, en, en_size, color, weight, align, EN_FONT)
            cy += line_h(role)
        else:
            _text(x, cy + en_size, en, en_size, color, weight, align, EN_FONT)
            _text(x, cy + en_size + zh_size * 1.05 + 1, zh, zh_size, ZH_C, weight, align, ZH_FONT)
            cy += line_h(role)
        if i < len(paras) - 1:
            cy += gap
    return cy


def card(x, y, w, header, paras, pad=14, fill=CARD, stroke=LINE, header_color=None, gap=5, ls="0.12em"):
    """A titled card that sizes itself to its content. Returns (height, content_bottom)."""
    head_h = line_h("eyebrow") + 8
    body_h = measure(paras, gap)
    h = pad + head_h + body_h + pad - 2
    box(x, y, w, h, fill, stroke)
    role, en, zh = header
    en_size, zh_size, weight, color = ROLES[role]
    hcolor = header_color or color
    if LANG == "zh":
        _text(x + pad, y + pad + zh_size, zh, zh_size, hcolor, weight, "start", ZH_FONT, ls)
    elif LANG == "en":
        _text(x + pad, y + pad + en_size, en, en_size, hcolor, weight, "start", EN_FONT, ls)
    else:
        _text(x + pad, y + pad + en_size, en, en_size, hcolor, weight, "start", EN_FONT, ls)
        _text(x + pad, y + pad + en_size + zh_size * 1.1, zh, zh_size, hcolor, weight, "start", ZH_FONT, ls)
    draw_paras(x + pad, y + pad + head_h, paras, gap)
    return h, y + pad + head_h + body_h


def inner_box(x, y, w, paras, pad=12, fill=SLATE_BG, stroke=LINE, gap=3):
    h = measure(paras, gap) + pad * 2
    box(x, y, w, h, fill, stroke, r=9)
    draw_paras(x + pad, y + pad, paras, gap)
    return h


# --------------------------------------------------------------------------- #
# the diagram
# --------------------------------------------------------------------------- #
def build(lang: str) -> tuple[str, int, int]:
    global LANG, parts
    LANG = lang
    parts = []

    WIDTH = 1740
    M = 44                     # outer margin
    LANE_Y = 132
    GAP = 16

    # ---------------- static geometry we need up front ----------------- #
    worker_stage_w, worker_stage_h = 186, 0  # height computed below
    cc = [0, 0, 0]                           # worker stage columns, filled below

    # ---------- title ------------------------------------------------- #
    head = [
        ("h1", "Purchase-order intake agent", "采购订单接入 Agent"),
        ("sub", "Template-free extraction, everything inside the client's own Azure tenant",
         "无模板抽取，全链路跑在客户自己的 Azure 租户内"),
    ]
    y = 34
    draw_paras(M, y, head, gap=8)

    # compliance chips (right aligned, approximate widths)
    chips = [
        ("No third-party SaaS", "无第三方 SaaS", RED),
        ("No per-page fees", "无按页收费", RED),
        ("Code owned day one", "第一天即归属客户", GREEN),
    ]
    x = WIDTH - M
    for en, zh, col in chips:
        label = {"both": f"{en} · {zh}", "en": en, "zh": zh}[lang]
        wpx = len(label) * 5.9 + 24
        x -= wpx + 8
        box(x, 40, wpx, 26, "#fff", LINE, r=13)
        _text(x + wpx / 2, 57, label, 10.2, col, "600", "middle", ZH_FONT)
    _text(WIDTH - M, 84, "Client Azure subscription · gpt-4.1 vision · ~$0.02–0.05 / order",
          10.5, MUTED, "400", "end", EN_FONT)
    _text(WIDTH - M, 98, "客户 Azure 订阅 · gpt-4.1 视觉 · 约 $0.02–0.05/单", 10, ZH_C, "400", "end", ZH_FONT)

    # ---------- column x positions ------------------------------------ #
    c1_x, c1_w = M, 372
    c2_x, c2_w = c1_x + c1_w + GAP, 244
    c3_x = c2_x + c2_w + GAP
    c4_w = 236
    c4_x = WIDTH - M - c4_w
    c3_w = c4_x - GAP - c3_x

    # ---------- 1 · intake -------------------------------------------- #
    p = [
        ("strong", "Outlook shared mailbox · Front · fax", "共享邮箱 · Front · 传真"),
        ("body", "new message with PDF attachments", "带 PDF 附件的新邮件"),
    ]
    intake_body_h = measure(p, 3) + 24
    intake_h = 34 + 20 + intake_body_h + 14 + (measure([
        ("strong", "Power Automate (thin trigger)", "Power Automate（薄触发层）"),
        ("body", "filter non-PDF · store · enqueue — no business logic", "过滤非 PDF · 存盘 · 入队，不放业务逻辑"),
    ], 3) + 24) + 16
    box(c1_x, LANE_Y, c1_w, intake_h)
    _text(c1_x + 16, LANE_Y + 26, "1 · INTAKE", 10.5, MUTED, "700", "start", EN_FONT, "0.14em")
    _text(c1_x + 16, LANE_Y + 40, "1 · 邮件接入", 10, ZH_C, "700", "start", ZH_FONT, "0.1em")
    inbox_h = inner_box(c1_x + 14, LANE_Y + 50, c1_w - 28, p)
    pa_y = LANE_Y + 50 + inbox_h + 22
    inner_box(c1_x + 14, pa_y, c1_w - 28, [
        ("strong", "Power Automate (thin trigger)", "Power Automate（薄触发层）"),
        ("body", "filter non-PDF · store · enqueue — no business logic", "过滤非 PDF · 存盘 · 入队，不放业务逻辑"),
    ], fill=AMBER_BG, stroke=AMBER_LINE)
    arrow(c1_x + c1_w / 2, LANE_Y + 50 + inbox_h + 2, c1_x + c1_w / 2, pa_y - 2)
    alt_y = pa_y + measure([
        ("strong", "Power Automate (thin trigger)", "Power Automate（薄触发层）"),
        ("body", "filter non-PDF · store · enqueue — no business logic", "过滤非 PDF · 存盘 · 入队，不放业务逻辑"),
    ], 3) + 38
    alt_h = inner_box(c1_x + 14, alt_y, c1_w - 28, [
        ("strong", "Alternative: Graph change subscription", "备选：Graph 变更订阅"),
        ("body", "same worker, and no Power Automate at all", "同一个 worker，完全不用 Power Automate"),
        ("body", "chosen at M1 once we see your mail flow", "M1 看到真实邮件流之后再定"),
    ], fill="#fff", stroke=LINE)
    intake_h = max(intake_h, alt_y + alt_h + 16 - LANE_Y)

    # ---------- 2 · buffer -------------------------------------------- #
    buf_paras = [
        ("strong", "Blob: original PDF", "Blob：原始 PDF"),
        ("micro", "sha256 · never mutated", "sha256 · 永不改写"),
    ]
    buf2_paras = [
        ("strong", "Storage Queue", "存储队列"),
        ("micro", "retry · dead-letter · idempotent", "重试 · 死信 · 幂等"),
    ]
    b1 = measure(buf_paras, 3) + 24
    b2 = measure(buf2_paras, 3) + 24
    buffer_h = 50 + b1 + 12 + b2 + 16
    box(c2_x, LANE_Y, c2_w, buffer_h)
    _text(c2_x + 14, LANE_Y + 26, "2 · BUFFER", 10.5, MUTED, "700", "start", EN_FONT, "0.14em")
    _text(c2_x + 14, LANE_Y + 40, "2 · 缓冲", 10, ZH_C, "700", "start", ZH_FONT, "0.1em")
    inner_box(c2_x + 12, LANE_Y + 50, c2_w - 24, buf_paras)
    inner_box(c2_x + 12, LANE_Y + 50 + b1 + 12, c2_w - 24, buf2_paras)

    # ---------- 3 · worker -------------------------------------------- #
    stages = [
        ("① Triage", "页面分流",
         [("body", "page roles by rules", "规则判定页面类型"),
          ("body", "cover / terms / blank", "封面 / 条款 / 空白页"),
          ("body", "never reach the model", "根本不送模型")], GREEN_BG, GREEN_LINE),
        ("② Render", "渲染",
         [("body", "PO pages only, 200 dpi", "只渲染订单页 200dpi"),
          ("body", "rotation correction", "自动旋转矫正"),
          ("body", "text layer if present", "有文本层优先用")], GREEN_BG, GREEN_LINE),
        ("③ Extract", "抽取",
         [("body", "Azure OpenAI gpt-4.1", "Azure OpenAI gpt-4.1"),
          ("body", "vision + strict schema", "视觉 + 严格 Schema"),
          ("body", "cites page + quote", "必须回引页码与原文")], BLUE_BG, BLUE_LINE),
        ("④ Match", "主数据匹配",
         [("body", "customer · ship-to", "客户 · 收货地址"),
          ("body", "part crosswalk · UOM", "料号交叉表 · 单位"),
          ("body", "price list", "价目表")], BLUE_BG, BLUE_LINE),
        ("⑤ Validate + route", "校验与路由",
         [("body", "arithmetic · evidence", "算术 · 证据回查"),
          ("body", "quality ceiling", "文档质量上限"),
          ("body", "auto / review / block", "自动 / 复核 / 拦截")], AMBER_BG, AMBER_LINE),
        ("⑥ Emit", "输出",
         [("body", "one CSV per order", "每单一个 CSV"),
          ("body", "atomic write", "原子写入"),
          ("body", "audit JSON + crops", "审计 JSON + 截图")], AMBER_BG, AMBER_LINE),
    ]
    stage_h = 26 + measure(stages[0][2], 3) + 16
    ladder = [
        ("arithmetic identity", "算术恒等式", "qty × price = extended · catches a missing page", "数量×单价=行金额，能抓漏页", 0.99),
        ("reference data", "参考主数据", "crosswalk · contract price · UOM", "料号交叉表 · 合同价 · 单位", 0.95),
        ("evidence re-check", "证据回查", "the cited quote must exist on that page", "引用原文必须在该页存在", 0.85),
        ("page-quality ceiling", "文档质量上限", "scanned ≤ 0.93 · handwritten ≤ 0.85", "扫描件 ≤0.93 · 手写 ≤0.85", 0.6),
        ("model self-report", "模型自述", "weakest — can only lower the score", "最弱，只能下调不能上调", 0.35),
    ]
    ladder_row_h = 22 if LANG == "both" else 18
    ladder_h = 44 + len(ladder) * ladder_row_h + 10
    worker_h = 46 + stage_h * 2 + 34 + ladder_h + 16

    box(c3_x, LANE_Y, c3_w, worker_h, BLUE_BG, BLUE_LINE, r=16, sw=1.6)
    _text(c3_x + 20, LANE_Y + 24, "3 · WORKER · Azure Container App  (our code, your subscription)",
          10.5, BLUE, "700", "start", EN_FONT, "0.08em")
    _text(c3_x + 20, LANE_Y + 38, "3 · Worker · Azure 容器应用（我们的代码，客户的订阅）",
          10, BLUE, "700", "start", ZH_FONT, "0.06em")

    cols = [c3_x + 18 + i * (worker_stage_w + 20) for i in range(3)]
    row1_y = LANE_Y + 50
    row2_y = row1_y + stage_h + 32
    coords = []
    for i, (en, zh, paras, fill, stroke) in enumerate(stages):
        col, row = i % 3, i // 3
        sx = cols[col]
        sy = row1_y if row == 0 else row2_y
        coords.append((sx, sy))
        box(sx, sy, worker_stage_w, stage_h, fill, stroke, r=10)
        _text(sx + 12, sy + 21, en, 12.2, INK, "700", "start", EN_FONT)
        _text(sx + 12, sy + 33, zh, 10.2, ZH_C, "700", "start", ZH_FONT)
        draw_paras(sx + 12, sy + 40, paras, 2)

    arrow(cols[0] + worker_stage_w + 1, row1_y + stage_h / 2, cols[1] - 1, row1_y + stage_h / 2, BLUE, 1.6)
    arrow(cols[1] + worker_stage_w + 1, row1_y + stage_h / 2, cols[2] - 1, row1_y + stage_h / 2, BLUE, 1.6)
    path(f"M{cols[2] + worker_stage_w / 2},{row1_y + stage_h + 1} V{row2_y - 16} H{cols[0] + worker_stage_w / 2} V{row2_y - 1}",
         BLUE, 1.6)
    arrow(cols[0] + worker_stage_w + 1, row2_y + stage_h / 2, cols[1] - 1, row2_y + stage_h / 2, BLUE, 1.6)
    arrow(cols[1] + worker_stage_w + 1, row2_y + stage_h / 2, cols[2] - 1, row2_y + stage_h / 2, BLUE, 1.6)

    # ladder panel
    lx, ly = c3_x + 18, row2_y + stage_h + 18
    lw = c3_w - 36
    box(lx, ly, lw, ladder_h, "#fff", BLUE_LINE, r=10)
    _text(lx + 14, ly + 20, "Confidence is computed, not claimed — strongest signal first",
          11.2, INK, "700", "start", EN_FONT)
    _text(lx + 14, ly + 33, "置信度是算出来的，不是模型说的 —— 信号从强到弱",
          10, ZH_C, "700", "start", ZH_FONT)
    for i, (en, zh, d_en, d_zh, bar) in enumerate(ladder):
        yy = ly + 46 + i * ladder_row_h
        _text(lx + 14, yy, f"{i + 1}  {en}", 10.2, INK, "600", "start", EN_FONT)
        if LANG == "both":
            _text(lx + 14, yy + 10, zh, 9.4, ZH_C, "400", "start", ZH_FONT)
            _text(lx + 186, yy, d_en, 9.8, MUTED, "400", "start", EN_FONT)
            _text(lx + 186, yy + 10, d_zh, 9.2, ZH_C, "400", "start", ZH_FONT)
        else:
            _text(lx + 186, yy, d_en, 9.8, MUTED, "400", "start", EN_FONT)
        bx = lx + lw - 92
        by = yy - 8 if LANG == "both" else yy - 7
        box(bx, by, 76, 6, "#e2e8f0", "#e2e8f0", r=3, sw=0)
        colr = GREEN if bar > 0.8 else AMBER if bar > 0.5 else RED
        box(bx, by, 76 * bar, 6, colr, colr, r=3, sw=0)

    # ---------- 4 · output -------------------------------------------- #
    o_paras = [
        ("strong", "ERP drop folder", "ERP 投递目录"),
        ("micro", "one CSV per order", "每单一个 CSV"),
        ("micro", "imported by your partner", "由集成商进程消费"),
    ]
    r_paras = [
        ("strong", "Review pack", "复核包"),
        ("micro", "Teams card + a crop of", "Teams 卡片 + 原文截图"),
        ("micro", "the exact printed line", "精确定位到那一行"),
    ]
    o1 = measure(o_paras, 3) + 24
    o2 = measure(r_paras, 3) + 24
    output_h = 50 + o1 + 12 + o2 + 16
    box(c4_x, LANE_Y, c4_w, output_h, CARD, GREEN_LINE)
    _text(c4_x + 14, LANE_Y + 26, "4 · OUTPUT", 10.5, MUTED, "700", "start", EN_FONT, "0.14em")
    _text(c4_x + 14, LANE_Y + 40, "4 · 输出", 10, ZH_C, "700", "start", ZH_FONT, "0.1em")
    inner_box(c4_x + 12, LANE_Y + 50, c4_w - 24, o_paras, fill=GREEN_BG, stroke=GREEN_LINE)
    inner_box(c4_x + 12, LANE_Y + 50 + o1 + 12, c4_w - 24, r_paras, fill=AMBER_BG, stroke=AMBER_LINE)

    # ---------- 5 · review loop --------------------------------------- #
    steps = [
        ("Rep fixes a field", "代表改一个字段", "in the review sheet or Teams card", "在复核页或 Teams 卡片里"),
        ("Re-emit CSV", "重出 CSV", "attempt + 1, the old file is archived", "attempt 递增，旧文件归档"),
        ("Sample audit", "抽样审计", "spot-check auto-ready orders", "对自动放行的单子抽检"),
        ("Metrics", "指标", "auto-rate · flag density · $/order", "自动率 · flag 密度 · 每单成本"),
    ]
    loop_y = LANE_Y + output_h + 14
    step_h = 46 if LANG == "both" else 32
    loop_h = 48 + len(steps) * step_h + 8
    box(c4_x, loop_y, c4_w, loop_h)
    _text(c4_x + 14, loop_y + 26, "5 · REVIEW LOOP", 10.5, MUTED, "700", "start", EN_FONT, "0.14em")
    _text(c4_x + 14, loop_y + 40, "5 · 人工闭环", 10, ZH_C, "700", "start", ZH_FONT, "0.1em")
    for i, (en, zh, d_en, d_zh) in enumerate(steps):
        yy = loop_y + 62 + i * step_h
        parts.append(f'<circle cx="{c4_x + 24}" cy="{yy - 4}" r="9" fill="{SLATE_BG}" stroke="{LINE}"/>')
        _text(c4_x + 24, yy, str(i + 1), 10, GREY, "700", "middle", EN_FONT)
        _text(c4_x + 42, yy - 2, en, 11, INK, "600", "start", EN_FONT)
        if LANG == "both":
            _text(c4_x + 42, yy + 10, zh, 9.8, ZH_C, "400", "start", ZH_FONT)
            _text(c4_x + 42, yy + 21, d_en, 9.4, MUTED, "400", "start", EN_FONT)
            _text(c4_x + 42, yy + 31, d_zh, 9.1, ZH_C, "400", "start", ZH_FONT)
        else:
            _text(c4_x + 42, yy + 12, d_en, 9.4, MUTED, "400", "start", EN_FONT)

    # ---------- rows 6 / 7 -------------------------------------------- #
    ref_items = [
        ("customers + aliases", "客户与别名", "email domains, printed-name aliases", "邮箱域名、打印名别名"),
        ("ship-to addresses", "收货地址", "scoped per customer — never global", "按客户隔离，绝不全局模糊匹配"),
        ("item crosswalk", "料号交叉表", "customer part · legacy · UPC → ERP SKU", "客户料号 · 旧料号 · UPC → ERP SKU"),
        ("price · UOM list", "价格与单位表", "contract price + canonical units", "合同价 + 规范化单位"),
    ]
    plat_items = [
        ("Managed Identity", "托管身份", "no keys on disk; the rest in Key Vault", "磁盘无密钥，其余放 Key Vault"),
        ("Application Insights", "应用洞察", "per-stage traces, cost per document", "分阶段追踪，每单成本"),
        ("Blob versioning · audit", "版本与审计", "original hash + prompt version kept", "原始哈希 + prompt 版本留档"),
        ("Bicep / azd deploy", "基础设施即代码", "whole stack in one command", "一条命令重建整套环境"),
    ]

    def grid_height(items) -> float:
        cell = max(measure([("strong", "", ""), ("micro", a, b), ("micro", c, d)], 2) for _, _, a, b, c, d in [(0, 0, *i[2:]) for i in items]) if False else 0
        # two rows of two
        return 40 + 2 * (measure([("strong", "", ""), ("micro", "", ""), ("micro", "", "")], 2) + 22)

    bottom_y = max(LANE_Y + max(intake_h, buffer_h, worker_h, output_h) + 34, loop_y + loop_h + 30)

    g6_w = 720
    g7_x = M + g6_w + GAP
    g7_w = WIDTH - M - g7_x
    cell_h = 46 if LANG == "both" else 32
    grid_h = 48 + 2 * cell_h + 6

    box(M, bottom_y, g6_w, grid_h)
    _text(M + 16, bottom_y + 24, "6 · REFERENCE DATA  (nightly sync, client-owned CSVs)",
          10.5, MUTED, "700", "start", EN_FONT, "0.1em")
    _text(M + 16, bottom_y + 38, "6 · 参考主数据（夜间同步，客户自有 CSV）", 10, ZH_C, "700", "start", ZH_FONT, "0.08em")
    for i, (en, zh, d_en, d_zh) in enumerate(ref_items):
        xx = M + 16 + (i % 2) * (g6_w / 2 - 8)
        yy = bottom_y + 60 + (i // 2) * cell_h
        _text(xx, yy, f"• {en}", 10.8, INK, "600", "start", EN_FONT)
        if LANG == "both":
            _text(xx + 10, yy + 11, d_en, 9.6, MUTED, "400", "start", EN_FONT)
            _text(xx + 10, yy + 21, d_zh, 9.2, ZH_C, "400", "start", ZH_FONT)
        else:
            _text(xx + 10, yy + 11, d_en, 9.6, MUTED, "400", "start", EN_FONT)

    box(g7_x, bottom_y, g7_w, grid_h)
    _text(g7_x + 16, bottom_y + 24, "7 · PLATFORM  (in your tenant, no long-lived secrets)",
          10.5, MUTED, "700", "start", EN_FONT, "0.1em")
    _text(g7_x + 16, bottom_y + 38, "7 · 平台（全部在客户租户内，无长期密钥）", 10, ZH_C, "700", "start", ZH_FONT, "0.08em")
    for i, (en, zh, d_en, d_zh) in enumerate(plat_items):
        xx = g7_x + 16 + (i % 2) * (g7_w / 2 - 8)
        yy = bottom_y + 60 + (i // 2) * cell_h
        _text(xx, yy, f"• {en}", 10.8, INK, "600", "start", EN_FONT)
        if LANG == "both":
            _text(xx + 10, yy + 11, d_en, 9.6, MUTED, "400", "start", EN_FONT)
            _text(xx + 10, yy + 21, d_zh, 9.2, ZH_C, "400", "start", ZH_FONT)
        else:
            _text(xx + 10, yy + 11, d_en, 9.6, MUTED, "400", "start", EN_FONT)

    # ---------- inter-card flows --------------------------------------- #
    arrow(c1_x + c1_w + 1, LANE_Y + 80, c2_x - 1, LANE_Y + 80, GREY, 1.8)
    _text(c1_x + c1_w + 2, LANE_Y + 72, "att.", 9.6, MUTED, "400", "start", EN_FONT)
    path(f"M{c2_x + c2_w + 1},{LANE_Y + 76} H{c3_x - 8} V{LANE_Y + 60} H{c3_x - 1}", GREY, 1.8)
    _text(c2_x + c2_w + 4, LANE_Y + 68, "job", 9.6, MUTED, "400", "start", EN_FONT)

    arrow(c3_x + c3_w + 1, LANE_Y + 64, c4_x - 1, LANE_Y + 64, GREEN, 1.8)
    arrow(c3_x + c3_w + 1, LANE_Y + 150, c4_x - 1, LANE_Y + 150, AMBER, 1.8)
    _text(c3_x + c3_w + 3, LANE_Y + 57, "CSV", 9.6, GREEN, "600", "start", EN_FONT)
    _text(c3_x + c3_w + 3, LANE_Y + 143, "flags", 9.6, AMBER, "600", "start", EN_FONT)

    # rep correction: output → back into ⑥ Emit
    emit_x, emit_y = coords[5]
    path(f"M{c4_x - 4},{LANE_Y + output_h + 2} H{c3_x + c3_w + 10} V{emit_y + stage_h + 14} H{emit_x + worker_stage_w + 1}",
         AMBER, 1.5, dash="5 4")

    # reference data → ④ Match
    match_x, match_y = coords[3]
    path(f"M{M + 200},{bottom_y - 1} V{LANE_Y + worker_h + 12} H{match_x + 30} V{match_y + stage_h + 1}",
         "#98a2b3", 1.4, dash="5 4")
    _text(M + 208, LANE_Y + worker_h + 6, "reference data feeds ④ Match / 主数据供给 ④ 匹配",
          9.6, MUTED, "600", "start", ZH_FONT)

    # ---------- footer -------------------------------------------------- #
    fy = bottom_y + grid_h + 34
    _text(M, fy, "Cover and terms pages are never sent to the model, so a 4-page fax costs two vision calls, not four.",
          10.5, MUTED, "400", "start", EN_FONT)
    _text(M, fy + 14, "封面页与条款页永远不送模型，所以 4 页传真只花 2 次视觉调用，而不是 4 次。",
          9.8, ZH_C, "400", "start", ZH_FONT)
    _text(M, fy + 34, "Everything above runs in the client's Azure subscription under the client's identity; the only external dependency is the model endpoint they own.",
          10.5, MUTED, "400", "start", EN_FONT)
    _text(M, fy + 48, "以上全部运行在客户 Azure 订阅内、以客户身份运行；唯一外部依赖是客户自己持有的模型端点。",
          9.8, ZH_C, "400", "start", ZH_FONT)

    H = int(fy + 76)
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{H}" viewBox="0 0 {WIDTH} {H}" role="img">'
    )
    defs = ["<defs>"]
    for color in (GREY, BLUE, GREEN, AMBER, "#98a2b3", "#b54708"):
        defs.append(
            f'<marker id="arrow-{color.strip("#")}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
        )
    defs.append("</defs>")
    body = "\n".join(parts)
    svg = "\n".join([header, *defs, f'<rect width="{WIDTH}" height="{H}" fill="{BG}"/>', body, "</svg>"])
    return svg, WIDTH, H


def main(argv: list[str]) -> int:
    targets = {"both": "architecture", "en": "architecture_en", "zh": "architecture_zh"}
    wanted = list(targets.values())
    if "--lang" in argv:
        wanted = [targets[argv[argv.index("--lang") + 1]]]
    for target in wanted:
        lang = {"architecture": "both", "architecture_en": "en", "architecture_zh": "zh"}[target]
        svg, w, h = build(lang)
        svg_path = OUT / f"{target}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        print(f"wrote {svg_path.name}  ({w}x{h})")
        try:
            import pymupdf

            doc = pymupdf.open(str(svg_path))
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
            pix.save(str(OUT / f"{target}.png"))
            print(f"wrote {target}.png  ({pix.width}x{pix.height})")
        except Exception as exc:  # pragma: no cover
            print("PNG export failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
