"""Tiny bilingual label table for everything a human reads.

Two audiences share these artefacts: the client (English, and only English when
we go live) and us (Chinese). So the default is "both" — English first, Chinese
underneath — and a single flag switches to either language.

    CHRONIK_LANG=both|en|zh   (env var, or --lang on the CLI)

Deliberately a dict, not gettext: 40 strings do not justify a message catalogue,
but they do justify keeping the two languages in one visible place so they cannot
drift apart.
"""

from __future__ import annotations

import os

LABELS: dict[str, tuple[str, str]] = {
    # ---- document / general ----
    "title": ("Purchase-order agent — review pack", "采购订单 Agent —— 复核包"),
    "subtitle": ("Synthetic sample documents; no client data.", "合成样本单据，不含客户数据。"),
    "documents": ("documents", "份单据"),
    "lines_parsed": ("lines parsed", "行已解析"),
    "straight_through": ("straight through", "无需人工直接放行"),
    "model_cost": ("model cost", "模型成本"),
    "avg_per_doc": ("avg / document", "平均每单耗时"),
    # ---- routes ----
    "auto_ready": ("Ready to import", "可直接导入"),
    "needs_review": ("Needs review", "需要复核"),
    "blocked": ("Blocked — cannot import", "已拦截 —— 不能导入"),
    # ---- table heads ----
    "severity": ("Severity", "级别"),
    "code": ("Code", "代码"),
    "field": ("Field", "字段"),
    "why": ("Why", "原因"),
    "extracted": ("Extracted", "抽取值"),
    "reference": ("Reference", "参考值"),
    "source": ("Source on the page", "原文位置"),
    "flags": ("Flags", "问题标记"),
    "resolved_lines": ("Resolved lines", "匹配后的行"),
    "line_no": ("#", "#"),
    "cust_item": ("Cust item", "客户料号"),
    "erp_item": ("ERP item", "ERP 物料"),
    "description": ("Description as printed", "单据原文描述"),
    "qty": ("Qty", "数量"),
    "uom": ("UOM", "单位"),
    "printed_price": ("Printed price", "单据价"),
    "erp_price": ("ERP price", "ERP 价"),
    "match": ("Match", "匹配方式"),
    "no_flags": (
        "No flags — every field reconciled against reference data and arithmetic.",
        "无任何标记 —— 所有字段都与主数据和算术核对一致。",
    ),
    "confidence": ("confidence", "置信度"),
    "ship_to": ("ship-to", "收货地址"),
    "lines": ("lines", "行"),
    "model": ("model", "模型"),
    # ---- CLI ----
    "cli_document": ("document", "单据"),
    "cli_route": ("route", "路由"),
    "cli_conf": ("conf", "置信"),
    "cli_flags": ("flags", "标记"),
    "csv_files": ("CSV files", "CSV 输出"),
    "review_pack": ("Review pack", "复核包"),
    "metrics": ("Metrics", "指标"),
    # ---- crops ----
    "crop_rotated": ("rotated", "已旋转"),
    "crop_text_search": ("located by text search", "按文本搜索定位"),
    "crop_bbox": ("model bbox", "模型给出的坐标框"),
    "crop_full_page": ("full page", "整页"),
}


def lang() -> str:
    v = (os.environ.get("CHRONIK_LANG") or "both").lower()
    return v if v in ("both", "en", "zh") else "both"


def t(key: str, sep: str = " · ") -> str:
    """Return the label in the active language (both = EN + 中文)."""
    en, zh = LABELS.get(key, (key, key))
    mode = lang()
    if mode == "en":
        return en
    if mode == "zh":
        return zh
    if en == zh:
        return en
    return f"{en}{sep}{zh}"


def bilingual(en: str, zh: str, sep: str = " · ") -> str:
    mode = lang()
    if mode == "en":
        return en
    if mode == "zh":
        return zh
    return f"{en}{sep}{zh}" if en != zh else en
