# ChronikShop

A **template-free purchase-order intake agent** for a US medical-supply distributor —
Microsoft 365 / Azure / Azure OpenAI, fully client-owned.
This repo holds the discussion documents and a runnable prototype.

![architecture](docs/diagram/architecture.png)

| Path | What it is |
|---|---|
| [`docs/04_proposal_bilingual.md`](docs/04_proposal_bilingual.md) | **Proposal (English + 中文对照)** — the paste-ready Upwork submission |
| [`docs/05_本地运行指南.md`](docs/05_本地运行指南.md) | **How to run it locally** — 10 minutes, no credentials |
| [`docs/01_方案总览.md`](docs/01_方案总览.md) | Architecture, model choice, the six design decisions, what the prototype proves |
| [`docs/02_里程碑与报价.md`](docs/02_里程碑与报价.md) | Milestones, work breakdown, pricing, support tiers |
| [`docs/03_风险与问题清单.md`](docs/03_风险与问题清单.md) | Risks and the questions to ask on the first call |
| [`docs/diagram/`](docs/diagram) | Architecture diagram as code (`build_arch.py` → SVG/PNG) |
| [`demo/`](demo) | End-to-end prototype: PDF → extract → match → validate → CSV + review pack |

## Quick start

```bash
git clone https://github.com/devops-huang/ChronikShop.git
cd ChronikShop/demo
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
python -m chronik.cli          # or: make demo
python -m pytest -q            # 20 passed
```

No credentials, no network, no client data — four synthetic sample orders
(clean PDF, sideways fax, handwriting, an unseen customer format) plus a
recorded-extraction replay so the whole pipeline is deterministic.

```
document             route          conf  lines  flags
clean_po.pdf         auto_ready     0.99      6  —
fax_multipage.pdf    needs_review   0.86      5  DOC_LOW_QUALITY, PRICE_MISMATCH, SHIP_TO_AMBIGUOUS, TOTAL_MISMATCH
handwritten_po.pdf   needs_review   0.85      5  DOC_LOW_QUALITY, HANDWRITTEN, ITEM_MATCHED_BY_DESCRIPTION
unknown_format.pdf   blocked        0.43      4  EVIDENCE_UNVERIFIED, ITEM_NOT_FOUND, MISSING_PO_NUMBER, ...
```

Outputs:

```
demo/out/csv/                 one CSV per order, ready for the ERP drop folder
demo/out/review/review.html   review sheet: every flag with a cropped screenshot of the source line
demo/out/review/*.json        per-order evidence pack (audit trail)
demo/out/metrics.json         auto-ready rate, confidence, cost per order, flag mix
```

Switch to the real model with `--live` (needs `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_DEPLOYMENT`); the provider is swapped behind a one-method
interface, so triage, matching, validation, CSV and review stay identical.

## Layout

```
demo/chronik/
  schema.py      pydantic contract: MailEnvelope, ExtractionResult, Flag, OrderAssessment
  pdfutil.py     rendering, rotation detection, bbox crops (PyMuPDF only)
  triage.py      page roles — cover/terms pages never reach the vision model
  prompts.py     versioned prompt + strict JSON schema notes
  extract.py     AzureOpenAIExtractor (vision, strict schema) / FixtureExtractor (replay)
  matching.py    customer / ship-to / item matching, scoped and ambiguity-aware
  normalize.py   UOM map, SKU keys, dates, addresses, decimals
  assess.py      evidence ladder: arithmetic > reference data > evidence > quality > model
  csvout.py      spec-driven CSV writer (config/settings.json)
  review.py      single-file HTML review pack with source crops
  pipeline.py    orchestration + metrics
  cli.py         `python -m chronik.cli [--live]`
```
