# ChronikShop

Working notes and a runnable prototype for a **template-free purchase-order intake agent**
(Microsoft 365 / Azure / Azure OpenAI, client-owned).

| Path | What it is |
|---|---|
| [`docs/01_方案总览.md`](docs/01_方案总览.md) | Architecture, model choice, the six design decisions, what the prototype proves |
| [`docs/02_里程碑与报价.md`](docs/02_里程碑与报价.md) | Milestones, work breakdown, pricing, support tiers |
| [`docs/03_风险与问题清单.md`](docs/03_风险与问题清单.md) | Risks and the questions to ask on the first call |
| [`demo/`](demo) | End-to-end prototype: PDF → extract → match → validate → CSV + review pack |

## Run the prototype

No credentials, no network, no client data — four synthetic sample orders
(clean PDF, sideways fax, handwriting, an unseen customer format) plus a
recorded-extraction replay so the whole pipeline is deterministic.

```bash
cd demo
make setup          # venv + pip install
make samples        # regenerate the synthetic PDFs (incl. fax/scan filtering)
make demo           # triage -> extract -> match -> validate -> CSV + review pack
make test           # 20 tests
```

Outputs:

```
demo/out/csv/                 one CSV per order, ready for the ERP drop folder
demo/out/review/review.html   review sheet: every flag with a cropped screenshot
demo/out/review/*.json        per-order evidence pack (audit trail)
demo/out/metrics.json         auto-ready rate, confidence, cost per order, flag mix
```

Switch to the real model with `--live` (needs `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_DEPLOYMENT`); the provider is swapped behind a one-method
interface, so triage, matching, validation, CSV and review all stay identical.

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
