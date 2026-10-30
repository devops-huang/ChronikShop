"""Review artefacts: one HTML sheet per batch, plus JSON per order.

Why HTML and not a queue table: the rep has to *see* the fax. A flag that says
"unit price differs by +3.9%" is useless next to a 300-dpi scan unless it is
attached to a cropped picture of the line. Crops are generated from the exact
quote the model cited, so the rep verifies the source, not the agent.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .i18n import t
from .pdfutil import Document, png_b64
from .schema import OrderAssessment, Severity

_SEV_COLOR = {Severity.BLOCK: "#b42318", Severity.REVIEW: "#b54708", Severity.INFO: "#475467"}
_ROUTE_KEYS = {"auto_ready": "auto_ready", "needs_review": "needs_review", "blocked": "blocked"}


def _crop_for(order: OrderAssessment, field: str | None, doc: Document) -> tuple[str | None, str]:
    """Highlight the source of a flag. Returns (base64 png, caption).

    Text-layer pages: search for the quoted string and crop tight.
    Scanned pages: use the bounding box the model returned when it gave one
    (that is why the schema carries ``bbox``); otherwise show the whole page
    rather than pretend we can point at the value.
    """
    if not field:
        return None, ""
    ev = order.extraction.evidence.get(field)
    if ev is None:
        # try a child path: "ship_to" -> "ship_to.street"
        for key, val in order.extraction.evidence.items():
            if key.startswith(field + "."):
                ev = val
                break
    if ev is None:
        # try a sibling on the same line: "line_items[1].customer_item_no"
        # -> "line_items[1].description". The model cited *something* for this
        # line; showing that crop is far better than showing nothing.
        m = re.match(r"^(line_items\[\d+\])\.", field)
        if m:
            for key, val in order.extraction.evidence.items():
                if key.startswith(m.group(1) + "."):
                    ev = val
                    break
    if ev is None:
        return None, ""
    rotation = 0
    for p in order.pages:
        if p.page_no == ev.page:
            rotation = p.rotation_applied
    caption = f"p.{ev.page}"
    if rotation:
        caption += f" · {t('crop_rotated', ' ')} {rotation}°"
    png = None
    if doc.page_view(ev.page).has_text_layer:
        png = doc.crop_around_text(ev.page, ev.quote or "", dpi=150)
        if png is not None:
            caption += f" · {t('crop_text_search')}"
    if png is None and ev.bbox:
        png = doc.crop_by_bbox(ev.page, ev.bbox, dpi=150, rotation=rotation)
        if png is not None:
            caption += f" · {t('crop_bbox')}"
    if png is None:
        png = doc.render_page_png(ev.page, rotation=rotation, dpi=80)
        caption += f" · {t('crop_full_page')}"
    return png_b64(png), caption


def _flag_rows(order: OrderAssessment, doc: Document, with_crops: bool) -> str:
    rows = []
    for f in sorted(order.flags, key=lambda x: list(Severity).index(x.severity)):
        crop, caption = _crop_for(order, f.field, doc) if with_crops else (None, "")
        color = _SEV_COLOR[f.severity]
        bits = [f"<tr><td><span class='pill' style='background:{color}'>{f.severity.value}</span></td>",
                f"<td><code>{html.escape(f.code.value)}</code></td>",
                f"<td><code>{html.escape(f.field or '')}</code></td>",
                f"<td>{html.escape(f.message)}</td>",
                f"<td class='num'>{html.escape(f.extracted or '')}</td>",
                f"<td class='num'>{html.escape(f.reference or '')}</td>"]
        if with_crops:
            img = f'<img src="data:image/png;base64,{crop}" />' if crop else ""
            bits.append(f"<td>{img}<div class='cap'>{html.escape(caption)}</div></td>")
        bits.append("</tr>")
        rows.append("".join(bits))
    if not rows:
        return f"<tr><td colspan='7' class='ok'>{html.escape(t('no_flags'))}</td></tr>"
    return "\n".join(rows)


def _line_rows(order: OrderAssessment) -> str:
    out = []
    for rl in order.resolved_lines:
        e = rl.extracted
        out.append(
            "<tr>"
            f"<td>{rl.line_no}</td>"
            f"<td><code>{html.escape(e.customer_item_no or '')}</code></td>"
            f"<td><code>{html.escape(rl.sku or '—')}</code></td>"
            f"<td class='desc'>{html.escape(e.description or '')}</td>"
            f"<td class='num'>{e.qty if e.qty is not None else ''}</td>"
            f"<td>{html.escape(e.uom or '')} → {html.escape(rl.uom or '?')}</td>"
            f"<td class='num'>{e.unit_price if e.unit_price is not None else ''}</td>"
            f"<td class='num'>{rl.erp_price if rl.erp_price is not None else ''}</td>"
            f"<td>{html.escape(rl.match_method)}</td>"
            "</tr>"
        )
    return "\n".join(out)


CSS = """
:root { --ink:#101828; --muted:#667085; --line:#eaecf0; --bg:#f9fafb; }
* { box-sizing: border-box; }
body { font: 14px/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: var(--ink); background: var(--bg); margin: 0; padding: 32px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: var(--muted); margin-bottom: 24px; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 20px;
        margin-bottom: 20px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.card h2 { font-size: 16px; margin: 0 0 2px; display: flex; gap: 10px; align-items: center; }
.meta { color: var(--muted); font-size: 12.5px; margin-bottom: 14px; }
.pill { display: inline-block; color: #fff; font-size: 11px; font-weight: 600; padding: 2px 7px;
        border-radius: 99px; text-transform: uppercase; letter-spacing: .02em; }
.route { font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 99px; border: 1px solid; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
     color: var(--muted); border-bottom: 1px solid var(--line); padding: 6px 8px; }
td { padding: 7px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.desc { max-width: 320px; }
td img { max-height: 110px; max-width: 190px; border: 1px solid var(--line); border-radius: 4px; }
.cap { font-size: 10.5px; color: var(--muted); margin-top: 3px; }
code { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; background: #f2f4f7;
       padding: 1px 4px; border-radius: 4px; }
.ok { color: #067647; }
.conf { font-weight: 700; font-variant-numeric: tabular-nums; }
.bar { height: 6px; background: #f2f4f7; border-radius: 99px; overflow: hidden; width: 160px; display:inline-block; vertical-align: middle;}
.bar > i { display: block; height: 100%; }
.summary { display: flex; gap: 28px; flex-wrap: wrap; }
.summary div { font-size: 12px; color: var(--muted); }
.summary b { display: block; font-size: 20px; color: var(--ink); }
h3 { font-size: 12.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 18px 0 2px; }
"""


def _conf_bar(value: float) -> str:
    pct = max(0.0, min(1.0, value)) * 100
    color = "#067647" if pct >= 92 else "#b54708" if pct >= 70 else "#b42318"
    return f"<span class='bar'><i style='width:{pct:.0f}%;background:{color}'></i></span> <span class='conf'>{pct:.0f}%</span>"


def render_html(
    results: list,
    sample_dir: str | Path,
    title: str | None = None,
    include_crops: bool = True,
) -> str:
    title = title or t("title")
    sample_dir = Path(sample_dir)
    cards = []
    for r in results:
        o: OrderAssessment = r.assessment
        doc = Document(sample_dir / o.source_filename)
        try:
            route_color = {"auto_ready": "#067647", "needs_review": "#b54708", "blocked": "#b42318"}[o.route]
            route_label = t(_ROUTE_KEYS[o.route])
            ext = o.extraction
            e = ext.order
            cards.append(
                f"""
    <div class="card">
      <h2>{html.escape(e.po_number or 'NO PO NUMBER')}
          <span class="route" style="color:{route_color};border-color:{route_color}">{html.escape(route_label)}</span></h2>
      <div class="meta">
        {html.escape(o.source_filename)} · {html.escape(o.customer_name or 'unknown customer')}
        {('· ' + html.escape(t('ship_to', ' ')) + ' ' + html.escape(o.ship_to_id)) if o.ship_to_id else ''}
        · {len(o.resolved_lines)} {html.escape(t('lines', ' '))} · {html.escape(t('confidence', ' '))} {_conf_bar(o.order_confidence)}
        · {html.escape(t('model', ' '))} {html.escape(ext.model)} · {ext.input_tokens + ext.output_tokens} tokens · ${ext.cost_usd:.4f}
        · {r.elapsed_s:.2f}s
      </div>
      <h3>{html.escape(t('flags'))}</h3>
      <table>
        <tr><th>{html.escape(t('severity'))}</th><th>{html.escape(t('code'))}</th><th>{html.escape(t('field'))}</th><th>{html.escape(t('why'))}</th><th>{html.escape(t('extracted'))}</th><th>{html.escape(t('reference'))}</th>{'<th>' + html.escape(t('source')) + '</th>' if include_crops else ''}</tr>
        {_flag_rows(o, doc, include_crops)}
      </table>
      <h3>{html.escape(t('resolved_lines'))}</h3>
      <table>
        <tr><th>{html.escape(t('line_no'))}</th><th>{html.escape(t('cust_item'))}</th><th>{html.escape(t('erp_item'))}</th><th>{html.escape(t('description'))}</th><th>{html.escape(t('qty'))}</th><th>{html.escape(t('uom'))}</th><th>{html.escape(t('printed_price'))}</th><th>{html.escape(t('erp_price'))}</th><th>{html.escape(t('match'))}</th></tr>
        {_line_rows(o)}
      </table>
    </div>"""
            )
        finally:
            doc.close()

    total = len(results)
    auto = sum(1 for r in results if r.assessment.route == "auto_ready")
    cost = sum(r.assessment.extraction.cost_usd for r in results)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="sub">{html.escape(t('subtitle', ' '))}</div>
  <div class="card">
    <div class="summary">
      <div><b>{total}</b> {html.escape(t('documents', ' '))}</div>
      <div><b>{sum(len(r.assessment.resolved_lines) for r in results)}</b> {html.escape(t('lines_parsed', ' '))}</div>
      <div><b>{auto}/{total}</b> {html.escape(t('straight_through', ' '))}</div>
      <div><b>${cost:.4f}</b> {html.escape(t('model_cost', ' '))}</div>
      <div><b>{sum(r.elapsed_s for r in results)/max(total,1):.2f}s</b> {html.escape(t('avg_per_doc', ' '))}</div>
    </div>
  </div>
  {''.join(cards)}
</body></html>"""


def write_review_pack(results: list, sample_dir: str | Path, out_dir: str | Path, include_crops: bool = True) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (out_dir / f"{r.assessment.order_id}.json").write_text(
            r.assessment.model_dump_json(indent=2)
        )
    path = out_dir / "review.html"
    path.write_text(render_html(results, sample_dir, include_crops=include_crops))
    return path
