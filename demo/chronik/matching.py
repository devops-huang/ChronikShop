"""Reference-data matching: customers, ship-to addresses, items.

Three rules drive this module:

1. **Scope before score.** A ship-to address is only ever compared against the
   matched customer's own addresses; an item only against that customer's
   crosswalk. Fuzzy matching across the whole file is how you ship the wrong
   product to the wrong hospital.
2. **Deterministic before fuzzy.** Part-number crosswalk hits are exact; the
   fuzzy ladder only starts when the crosswalk misses.
3. **Ambiguity is a result, not a failure.** When two candidates score within a
   few points of each other we return both and flag — we never silently pick
   the top one.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from rapidfuzz import fuzz

from .normalize import (
    canonical_uom,
    normalize_street,
    normalize_text,
    normalize_zip,
    sku_key,
)
from .schema import Party

SHIP_TO_AUTO = 90.0
SHIP_TO_REVIEW = 76.0
ITEM_DESC_AUTO = 93.0
ITEM_DESC_REVIEW = 86.0


# --------------------------------------------------------------------------- #
# reference data
# --------------------------------------------------------------------------- #
@dataclass
class Customer:
    customer_id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    email_domains: list[str] = field(default_factory=list)


@dataclass
class ShipTo:
    ship_to_id: str
    customer_id: str
    name: str
    street: str
    city: str
    state: str
    zip: str


@dataclass
class Item:
    sku: str
    description: str
    uom: str
    price: Decimal
    active: bool = True


@dataclass
class CrosswalkEntry:
    sku: str
    customer_id: str
    part_no: str
    part_type: str  # customer | legacy | upc


class ReferenceData:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.customers: dict[str, Customer] = {}
        self.ship_tos: dict[str, ShipTo] = {}
        self.items: dict[str, Item] = {}
        self.crosswalk_by_key: dict[tuple[str, str], list[CrosswalkEntry]] = {}
        self._load()

    def _rows(self, name: str) -> list[dict]:
        path = self.dir / name
        if not path.exists():
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _load(self) -> None:
        for r in self._rows("customers.csv"):
            self.customers[r["customer_id"]] = Customer(
                customer_id=r["customer_id"],
                name=r["name"],
                aliases=[a for a in (r.get("aliases") or "").split("|") if a],
                email_domains=[d.strip().lower() for d in (r.get("email_domains") or "").split("|") if d.strip()],
            )
        for r in self._rows("ship_to.csv"):
            self.ship_tos[r["ship_to_id"]] = ShipTo(
                ship_to_id=r["ship_to_id"],
                customer_id=r["customer_id"],
                name=r["name"],
                street=r["street"],
                city=r["city"],
                state=r["state"],
                zip=r["zip"],
            )
        for r in self._rows("items.csv"):
            self.items[r["sku"]] = Item(
                sku=r["sku"],
                description=r["description"],
                uom=r["uom"],
                price=Decimal(r["price"]),
                active=(r.get("status", "active").lower() != "inactive"),
            )
        for r in self._rows("item_crosswalk.csv"):
            e = CrosswalkEntry(
                sku=r["sku"],
                customer_id=r["customer_id"],
                part_no=r["part_no"],
                part_type=r.get("part_type", "customer"),
            )
            self.crosswalk_by_key.setdefault((e.customer_id, sku_key(e.part_no)), []).append(e)
            # Only genuinely global numbering schemes are searchable across
            # customers. A *customer* part number must never resolve for
            # somebody else's order - that is how you ship the wrong product.
            if e.part_type in ("legacy", "upc", "manufacturer"):
                self.crosswalk_by_key.setdefault(("*", sku_key(e.part_no)), []).append(e)

    # -- customers -------------------------------------------------------- #
    def match_customer(
        self, sender_email: str, printed_name: str | None, bill_to: Party | None = None
    ) -> tuple[str | None, float, str, list[str]]:
        """Return (customer_id, score, method, competing_candidates)."""
        domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""
        hits = [c for c in self.customers.values() if domain and domain in c.email_domains]
        if len(hits) == 1:
            return hits[0].customer_id, 100.0, "sender_domain", []
        if len(hits) > 1:
            return None, 100.0, "sender_domain_ambiguous", [h.customer_id for h in hits]

        candidates: list[tuple[float, str]] = []
        names = [printed_name or ""]
        if bill_to and bill_to.name:
            names.append(bill_to.name)
        for raw in [n for n in names if n.strip()]:
            probe = normalize_text(raw)
            for c in self.customers.values():
                for alias in [c.name, *c.aliases]:
                    score = fuzz.token_set_ratio(probe, normalize_text(alias))
                    if score >= 80:
                        candidates.append((float(score), c.customer_id))
        if not candidates:
            return None, 0.0, "none", []
        candidates.sort(reverse=True)
        best_score, best_id = candidates[0]
        rivals = [cid for sc, cid in candidates[1:] if sc >= best_score - 3 and cid != best_id]
        if rivals:
            return None, best_score, "name_ambiguous", [best_id, *rivals]
        return best_id, best_score, "printed_name", []

    # -- ship-to ---------------------------------------------------------- #
    def match_ship_to(self, customer_id: str | None, ship_to: Party) -> tuple[str | None, float, str, list[str]]:
        if not customer_id:
            return None, 0.0, "no_customer", []
        pool = [s for s in self.ship_tos.values() if s.customer_id == customer_id]
        if not pool:
            return None, 0.0, "customer_has_no_addresses", []
        probe_street = normalize_street(ship_to.street)
        probe_city = normalize_text(ship_to.city)
        probe_zip = normalize_zip(ship_to.zip)
        scored: list[tuple[float, str]] = []
        for s in pool:
            street = fuzz.token_set_ratio(probe_street, normalize_street(s.street)) if probe_street else 0.0
            city = fuzz.token_set_ratio(probe_city, normalize_text(s.city)) if probe_city else 0.0
            zip_score = 100.0 if probe_zip and probe_zip == normalize_zip(s.zip) else 0.0
            # zip is decisive when present; street carries the rest
            score = 0.62 * street + 0.18 * city + 0.20 * zip_score
            if zip_score and street >= 80:
                score = max(score, 95.0)
            scored.append((score, s.ship_to_id))
        scored.sort(reverse=True)
        best, best_id = scored[0]
        rivals = [sid for sc, sid in scored[1:] if sc >= best - 4][:3]
        return best_id, round(best, 1), "address", rivals

    # -- items ------------------------------------------------------------ #
    def match_item(self, customer_id: str | None, part_no: str | None, description: str | None):
        """Ladder: crosswalk -> sku -> description. Returns dict."""
        key = sku_key(part_no)
        if key:
            for scope in ([customer_id] if customer_id else []) + ["*"]:
                entries = self.crosswalk_by_key.get((scope, key)) or []
                skus = {e.sku for e in entries}
                if len(skus) == 1:
                    e = entries[0]
                    return {
                        "sku": e.sku,
                        "method": "customer_part" if e.part_type == "customer" else f"{e.part_type}_part",
                        "score": 100.0,
                        "candidates": [],
                    }
                if len(skus) > 1:
                    return {"sku": None, "method": "crosswalk_ambiguous", "score": 100.0, "candidates": sorted(skus)}
            if key in {sku_key(k) for k in self.items}:
                hit = next(k for k in self.items if sku_key(k) == key)
                return {"sku": hit, "method": "sku", "score": 100.0, "candidates": []}

        if description:
            probe = normalize_text(description)
            scored = [
                (float(fuzz.token_set_ratio(probe, normalize_text(i.description))), sku)
                for sku, i in self.items.items()
                if i.active
            ]
            scored = [s for s in scored if s[0] >= ITEM_DESC_REVIEW]
            scored.sort(reverse=True)
            if scored:
                best, best_sku = scored[0]
                rivals = [sku for sc, sku in scored[1:] if sc >= best - 2][:3]
                if rivals:
                    return {
                        "sku": None,
                        "method": "description_ambiguous",
                        "score": best,
                        "candidates": [best_sku, *rivals],
                    }
                return {"sku": best_sku, "method": "description", "score": best, "candidates": []}
        return {"sku": None, "method": "none", "score": 0.0, "candidates": []}

    def uom_for(self, sku: str) -> str | None:
        item = self.items.get(sku)
        if not item:
            return None
        return canonical_uom(item.uom)[0] or item.uom

    def price_for(self, sku: str) -> Decimal | None:
        item = self.items.get(sku)
        return item.price if item else None
