# ChronikShop

**采购订单 AI Agent · 方案与可运行原型** — 无模板抽取、校验优先、全链路跑在客户自己的 Azure 订阅内。
**Purchase-order intake agent — design + runnable prototype.** Template-free extraction, validation-first, everything inside the client's own Azure tenant.

![architecture](docs/diagram/architecture.png)

> 交付物默认**中英双语**；上客户时用英文版（`--lang en`，或 `docs/04_proposal_bilingual.md` 的英文部分）。
> *Deliverables are bilingual by default; switch everything to English with `--lang en` when it goes to the client.*

## 文档 · Documents

| 路径 · Path | 内容 · What it is |
|---|---|
| [`docs/04_proposal_bilingual.md`](docs/04_proposal_bilingual.md) | **投标提案 · Proposal**（英文正文 + 中文对照 / English then Chinese） |
| [`docs/05_本地运行指南.md`](docs/05_本地运行指南.md) | **本地跑起来 · Run it locally**（10 分钟，零凭证） |
| [`docs/01_方案总览.md`](docs/01_方案总览.md) | 架构、模型选型、六个关键决策 · Architecture, model choice, six decisions |
| [`docs/02_里程碑与报价.md`](docs/02_里程碑与报价.md) | 里程碑与报价 · Milestones, effort, pricing, support tiers |
| [`docs/03_风险与问题清单.md`](docs/03_风险与问题清单.md) | 风险与首会问题 · Risks (HIPAA first) + first-call questions |
| [`docs/diagram/`](docs/diagram) | 架构图即代码 · Diagram as code（`build_arch.py` → SVG/PNG，双语/EN/中文三版） |
| [`demo/`](demo) | 端到端原型 · End-to-end prototype |

## 快速开始 · Quick start

> **需要 Python 3.9+**（CentOS/RHEL 自带的 `python3` 常见是 3.6，不够用）。
> 先自检：`python3 scripts/doctor.py`。不想装 Python 就直接 `docker compose run --rm demo`。
> *Needs Python 3.9+ (CentOS/RHEL stock `python3` is often 3.6). Preflight: `python3 scripts/doctor.py`. Zero-install: `docker compose run --rm demo`.*

```bash
git clone https://github.com/devops-huang/ChronikShop.git
cd ChronikShop/demo
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
python -m chronik.cli          # 或 make demo / or: make demo
```

无需凭证、无需联网、无客户数据 —— 4 份合成样本（干净 PDF / 横向传真 / 手写 / 陌生格式）+ 录制回放，全流程确定性可复现。
*No credentials, no network, no client data: four synthetic sample orders plus a recorded-extraction replay, so the pipeline is fully deterministic.*

```
document / 单据          route / 路由                    conf  lines  flags
clean_po.pdf            Ready to import / 可直接导入    0.99      6  —
fax_multipage.pdf       Needs review / 需要复核         0.86      5  DOC_LOW_QUALITY, PRICE_MISMATCH, SHIP_TO_AMBIGUOUS, TOTAL_MISMATCH
handwritten_po.pdf      Needs review / 需要复核         0.85      5  DOC_LOW_QUALITY, HANDWRITTEN, ITEM_MATCHED_BY_DESCRIPTION
unknown_format.pdf      Blocked / 已拦截                0.43      4  EVIDENCE_UNVERIFIED, ITEM_NOT_FOUND, MISSING_PO_NUMBER, ...
```

产物 · Outputs：

```
demo/out/csv/                每单一个 CSV · one CSV per order (ERP drop folder)
demo/out/review/review.html  复核页，含每条的原文截图 · review sheet with source crops
demo/out/review/preview_*.png 每单一张复核卡（双语）· one bilingual PNG card per order
demo/out/review/*.json       单证审计包 · per-order evidence pack
demo/out/metrics.json        放行率、置信度、每单成本 · auto-rate, confidence, cost per order
```

切换真实模型 · switch to the live model：

```bash
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_OPENAI_DEPLOYMENT="gpt-4.1"
python -m chronik.cli --live
```

语言开关 · language switch（所有产物通用 / applies to every artefact）：

```bash
python -m chronik.cli --lang en        # 全英文（上客户）· English only
python -m chronik.cli --lang zh        # 全中文 · Chinese only
CHRONIK_LANG=en python -m chronik.preview
```

## 目录 · Layout

```
demo/chronik/
  schema.py      pydantic 契约 · MailEnvelope, ExtractionResult, Flag, OrderAssessment
  pdfutil.py     渲染、旋转检测、bbox 裁剪（仅 PyMuPDF）
  triage.py      页面分流 —— 封面/条款页永不送模型
  prompts.py     版本化 prompt + 严格 JSON schema
  extract.py     AzureOpenAIExtractor（生产/视觉）/ FixtureExtractor（离线回放）
  matching.py    客户 / 收货地址 / 料号匹配：先收窄范围，歧义不猜
  normalize.py   UOM 映射、料号归一、日期、地址、金额
  assess.py      证据阶梯：算术 > 主数据 > 证据回查 > 文档质量 > 模型自述
  csvout.py      声明式 CSV 写出（config/settings.json）
  review.py      单文件 HTML 复核页（含原文截图）
  preview.py     双语 PNG 复核卡
  i18n.py        双语文案表 · bilingual label table
  pipeline.py    编排 + 指标
  cli.py         `python -m chronik.cli [--live] [--lang both|en|zh]`
```
