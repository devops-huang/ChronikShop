"""The pipeline: mail envelope + PDF -> assessment -> CSV + review artefacts.

Stages are pure functions where possible so each one is testable in isolation:

    triage -> extract -> assess(match+validate+score) -> route -> emit

The orchestrator is deliberately boring. Every non-deterministic step is behind
the :class:`~chronik.extract.Extractor` protocol so it can be replayed.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .assess import assess
from .csvout import CsvSpec, write_order_csv
from .extract import Extractor, FixtureExtractor
from .matching import ReferenceData
from .pdfutil import Document
from .schema import MailEnvelope, OrderAssessment, PageRole
from .triage import pages_to_extract, triage


@dataclass
class Settings:
    csv_spec: CsvSpec
    price_policy: str = "extracted"
    auto_ready_min_confidence: float = 0.92
    emit_blocked_orders: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = json.loads(Path(path).read_text())
        return cls(
            csv_spec=CsvSpec(raw["csv_spec"]),
            price_policy=raw.get("price_policy", "extracted"),
            auto_ready_min_confidence=raw.get("routing", {}).get("auto_ready_min_confidence", 0.92),
            emit_blocked_orders=raw.get("routing", {}).get("emit_blocked_orders", False),
        )


@dataclass
class ProcessResult:
    assessment: OrderAssessment
    csv_path: Path | None
    elapsed_s: float
    stages: dict[str, float] = field(default_factory=dict)


def order_id_for(filename: str, po_number: str | None) -> str:
    stem = Path(filename).stem
    digest = hashlib.sha1(stem.encode()).hexdigest()[:6].upper()
    return f"{po_number or 'NOPO'}-{digest}"


def process_document(
    pdf_path: str | Path,
    env: MailEnvelope,
    ref: ReferenceData,
    extractor: Extractor,
    settings: Settings,
    out_dir: str | Path,
) -> ProcessResult:
    t_start = time.perf_counter()
    stages: dict[str, float] = {}
    pdf_path = Path(pdf_path)

    with Document(pdf_path) as doc:
        t = time.perf_counter()
        views = doc.page_views()
        base = triage(views)
        hints = {}
        if any(not v.has_text_layer for v in views):
            hints = extractor.page_roles(doc, base)
        pages = triage(views, hints) if hints else base
        numbers = pages_to_extract(pages) or [1]
        stages["triage"] = round(time.perf_counter() - t, 4)

        t = time.perf_counter()
        extraction = extractor.extract(doc, pages, numbers)
        stages["extract"] = round(time.perf_counter() - t, 4)

        t = time.perf_counter()
        oid = order_id_for(pdf_path.name, extraction.order.po_number)
        result = assess(extraction, env, doc, ref, oid, pages=pages)
        # keep page info on the assessment for the review sheet
        from .schema import PageInfo

        result.pages = [PageInfo.model_validate(p.model_dump()) for p in pages]
        stages["assess"] = round(time.perf_counter() - t, 4)

        # ---- routing ---------------------------------------------------- #
        emit_dir = Path(out_dir) / "csv"
        if result.route == "blocked" and not settings.emit_blocked_orders:
            csv_path = None
        else:
            csv_path = write_order_csv(result, settings.csv_spec, emit_dir, settings.price_policy)

    return ProcessResult(
        assessment=result,
        csv_path=csv_path,
        elapsed_s=round(time.perf_counter() - t_start, 3),
        stages=stages,
    )


# --------------------------------------------------------------------------- #
# batch entry point used by the CLI and by tests
# --------------------------------------------------------------------------- #
def run_batch(
    sample_dir: str | Path,
    manifest_path: str | Path,
    ref: ReferenceData,
    extractor: Extractor,
    settings: Settings,
    out_dir: str | Path,
) -> list[ProcessResult]:
    sample_dir = Path(sample_dir)
    manifest = _load_manifest(manifest_path)
    results: list[ProcessResult] = []
    for item in manifest:
        pdf = sample_dir / item["file"]
        if not pdf.exists():
            continue
        env = MailEnvelope(**{k: v for k, v in item.items() if k != "file"})
        results.append(process_document(pdf, env, ref, extractor, settings, out_dir))
    return results


def _load_manifest(path: str | Path) -> list[dict]:
    raw = json.loads(Path(path).read_text())
    return raw["messages"]


def default_extractor(replay_dir: str | Path | None, **azure_kwargs) -> Extractor:
    """Pick the provider. No credentials -> replay; credentials -> Azure OpenAI."""
    if replay_dir:
        return FixtureExtractor(replay_dir)
    from .extract import AzureOpenAIExtractor

    return AzureOpenAIExtractor(**azure_kwargs)


def write_metrics(results: list[ProcessResult], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(results)
    auto = sum(1 for r in results if r.assessment.route == "auto_ready")
    review = sum(1 for r in results if r.assessment.route == "needs_review")
    blocked = sum(1 for r in results if r.assessment.route == "blocked")
    cost = sum(r.assessment.extraction.cost_usd for r in results)
    lines = sum(len(r.assessment.resolved_lines) for r in results)
    flag_counts: dict[str, int] = {}
    for r in results:
        for f in r.assessment.flags:
            flag_counts[f.code.value] = flag_counts.get(f.code.value, 0) + 1
    payload = {
        "documents": total,
        "lines": lines,
        "routes": {"auto_ready": auto, "needs_review": review, "blocked": blocked},
        "auto_ready_rate": round(auto / total, 3) if total else 0.0,
        "avg_confidence": round(sum(r.assessment.order_confidence for r in results) / total, 3) if total else 0.0,
        "avg_seconds_per_doc": round(sum(r.elapsed_s for r in results) / total, 3) if total else 0.0,
        "model_cost_usd_total": round(cost, 4),
        "model_cost_usd_per_doc": round(cost / total, 4) if total else 0.0,
        "flag_counts": dict(sorted(flag_counts.items(), key=lambda kv: -kv[1])),
        "per_document": [
            {
                "order_id": r.assessment.order_id,
                "file": r.assessment.source_filename,
                "route": r.assessment.route,
                "confidence": r.assessment.order_confidence,
                "lines": len(r.assessment.resolved_lines),
                "flags": [f.code.value for f in r.assessment.flags],
                "seconds": r.elapsed_s,
                "cost_usd": r.assessment.extraction.cost_usd,
            }
            for r in results
        ],
    }
    path = out_dir / "metrics.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


__all__ = [
    "Settings",
    "ProcessResult",
    "process_document",
    "run_batch",
    "write_metrics",
    "default_extractor",
    "PageRole",
]
