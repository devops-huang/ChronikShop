"""CSV writer driven by a declarative column spec (config/settings.json).

The spec lives in a drop-in-able JSON file, not in code. When the integration
partner revises the format — and they will, twice — that is a config diff, not
a refactor, and the same spec drives the fixture tests.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .schema import OrderAssessment


class CsvSpec:
    def __init__(self, spec: dict):
        self.spec = spec
        self.columns: list[dict] = spec["columns"]
        self.filename_pattern: str = spec.get("filename_pattern", "PO_{po_number}.csv")
        self.version: str = spec.get("version", "0")

    @classmethod
    def load(cls, path: str | Path) -> "CsvSpec":
        settings = json.loads(Path(path).read_text())
        return cls(settings["csv_spec"])

    @property
    def header(self) -> list[str]:
        return [c["name"] for c in self.columns]

    @property
    def required(self) -> list[str]:
        return [c["name"] for c in self.columns if c.get("required")]


def _fmt(value, col: dict) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        fmt = col.get("format", "0.00")
        frac = fmt.split(".")[1] if "." in fmt else ""
        places = len(frac)
        if "#" in frac:  # "0.####" -> at most N places, no trailing zeros
            text = f"{value:.{places}f}".rstrip("0").rstrip(".")
            return text or "0"
        return f"{value:.{places}f}"
    if isinstance(value, date):
        return value.strftime(col.get("format", "%Y-%m-%d"))
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _page_hint(order: OrderAssessment, line_idx: int) -> str:
    ev = order.extraction.evidence.get(f"line_items[{line_idx}]")
    if ev is None:
        ev = order.extraction.evidence.get(f"line_items[{line_idx}].qty")
    return str(ev.page) if ev else ""


def rows_for(order: OrderAssessment, price_policy: str = "extracted") -> list[dict]:
    o = order.extraction.order
    rows: list[dict] = []
    for idx, rl in enumerate(order.resolved_lines):
        src = rl.extracted
        price = rl.unit_price
        if price_policy == "erp" and rl.erp_price is not None:
            price = rl.erp_price
        rows.append(
            {
                "ORDER_REF": order.order_id,
                "PO_NUMBER": o.po_number,
                "CUSTOMER_ID": order.customer_id,
                "ORDER_DATE": o.order_date,
                "SHIP_TO_ID": order.ship_to_id,
                "REQUESTED_DATE": src.requested_date or o.requested_ship_date,
                "LINE_NO": rl.line_no,
                "ITEM": rl.sku,
                "CUSTOMER_ITEM": src.customer_item_no,
                "QTY": src.qty,
                "UOM": rl.uom or src.uom,
                "UNIT_PRICE": price,
                "SHIP_VIA": o.ship_via,
                "CARRIER_ACCOUNT": o.carrier_account,
                "SPECIAL_INSTRUCTIONS": o.special_instructions if idx == 0 else None,
                "SOURCE_FILE": order.source_filename,
                "SOURCE_PAGE": _page_hint(order, idx),
            }
        )
    return rows


def write_order_csv(
    order: OrderAssessment,
    spec: CsvSpec,
    out_dir: str | Path,
    price_policy: str = "extracted",
) -> Path | None:
    """Write one CSV per order. Returns the path, or None if nothing was written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = rows_for(order, price_policy)
    if not rows:
        return None
    name = spec.filename_pattern.format(
        customer_id=order.customer_id or "UNKNOWN",
        po_number=order.extraction.order.po_number or "NO_PO",
        order_ref=order.order_id,
        attempt=1,  # re-emits after a rep correction increment this
    )
    path = out_dir / name
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=spec.header, extrasaction="ignore", lineterminator="\r\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k), col) for k, col in zip(spec.header, spec.columns)})
    return path
