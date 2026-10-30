"""CLI entry point.

    python -m chronik.cli                 # replay fixtures against the samples (offline)
    python -m chronik.cli --live          # call Azure OpenAI (needs env vars)
    python -m chronik.cli --confusion     # flag statistics per document
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .matching import ReferenceData
from .pipeline import Settings, default_extractor, run_batch, write_metrics
from .review import write_review_pack

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chronik PO agent prototype")
    ap.add_argument("--samples", default=str(ROOT / "samples"))
    ap.add_argument("--manifest", default=str(ROOT / "samples" / "mail_manifest.json"))
    ap.add_argument("--data", default=str(ROOT / "data" / "erp"))
    ap.add_argument("--fixtures", default=str(ROOT / "fixtures"))
    ap.add_argument("--settings", default=str(ROOT / "config" / "settings.json"))
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--live", action="store_true", help="use Azure OpenAI instead of replayed fixtures")
    ap.add_argument("--no-crops", action="store_true", help="do not embed page crops in the review sheet")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    settings = Settings.load(args.settings)
    ref = ReferenceData(args.data)

    if args.live:
        extractor = default_extractor(
            None,
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1"),
        )
    else:
        extractor = default_extractor(args.fixtures)

    results = run_batch(args.samples, args.manifest, ref, extractor, settings, args.out)
    metrics_path = write_metrics(results, args.out)
    review_path = write_review_pack(results, args.samples, Path(args.out) / "review", include_crops=not args.no_crops)

    if not args.quiet:
        print(f"{'document':22s} {'route':14s} {'conf':>5s}  {'lines':>5s}  flags")
        for r in results:
            a = r.assessment
            codes = ", ".join(sorted({f.code.value for f in a.flags})) or "—"
            print(f"{a.source_filename:22s} {a.route:14s} {a.order_confidence:5.2f}  {len(a.resolved_lines):5d}  {codes}")
        print(f"\nCSV files   : {Path(args.out) / 'csv'}")
        print(f"Review pack : {review_path}")
        print(f"Metrics     : {metrics_path}")
        print("\n" + json.dumps(json.loads(metrics_path.read_text())["routes"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
