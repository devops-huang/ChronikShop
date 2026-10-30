"""Extraction providers.

Two interchangeable implementations of the same one-method interface:

* :class:`AzureOpenAIExtractor` – the production path (vision model in the
  customer's own Azure OpenAI deployment, JSON-schema structured output).
* :class:`FixtureExtractor` – deterministic replay of *recorded* model output
  for the sample documents, so the whole pipeline (triage, validation,
  matching, CSV, review sheet) can be developed, unit-tested and demoed with
  no credentials and no network.

Swapping providers is one line in :mod:`chronik.pipeline`, which is exactly what
the regression harness needs: recorded fixtures become deterministic goldens.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .pdfutil import Document
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from .schema import Evidence, ExtractedOrder, ExtractionResult, PageInfo, PageRole, PageRoleHint


class Extractor(Protocol):
    name: str

    def extract(self, doc: Document, pages: list[PageInfo], page_numbers: list[int]) -> ExtractionResult: ...

    def page_roles(self, doc: Document, pages: list[PageInfo]) -> dict[int, PageRoleHint]:
        """Cheap page classification for pages without a usable text layer."""
        ...


# --------------------------------------------------------------------------- #
# production: Azure OpenAI, vision + structured output
# --------------------------------------------------------------------------- #
@dataclass
class ModelPrice:
    input_per_1m: float
    output_per_1m: float


# list prices in the customer's own Azure subscription (USD / 1M tokens)
PRICE_TABLE = {
    "gpt-4.1": ModelPrice(2.00, 8.00),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60),
}


class AzureOpenAIExtractor:
    """Vision extraction with page images + text layer, strict JSON schema out."""

    name = "azure-openai"

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-10-21",
        dpi: int = 200,
        timeout_s: int = 120,
        classifier_deployment: str | None = None,
    ) -> None:
        from openai import AzureOpenAI  # local import: not needed for offline demo

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=None,  # in Azure: managed identity token provider
            timeout=timeout_s,
        )
        self.deployment = deployment
        self.classifier_deployment = classifier_deployment or deployment
        self.dpi = dpi

    # -- helpers ---------------------------------------------------------- #
    def _schema(self) -> dict:
        schema = ExtractedOrder.model_json_schema()
        return _strictify(schema)

    def _content(self, doc: Document, pages: list[PageInfo], page_numbers: list[int]) -> list[dict]:
        skipped = [p.page_no for p in pages if p.page_no not in page_numbers]
        text_blob = []
        for no in page_numbers:
            text = doc.page_view(no).text.strip()
            text_blob.append(f"--- page {no} ---\n{text[:6000] if text else '(no text layer)'}")
        blocks: list[dict] = [
            {
                "type": "text",
                "text": USER_PROMPT_TEMPLATE.format(
                    filename=doc.path.name,
                    page_list=page_numbers,
                    skipped_pages=skipped,
                    page_text="\n".join(text_blob),
                ),
            }
        ]
        for no in page_numbers:
            png = doc.render_page_png(no, dpi=self.dpi)
            import base64

            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode(), "detail": "high"},
                }
            )
        return blocks

    # -- page classification (text-less pages only) ----------------------- #
    def page_roles(self, doc: Document, pages: list[PageInfo]) -> dict[int, PageRoleHint]:
        from .prompts import PAGE_CLASSIFIER_PROMPT

        hints: dict[int, PageRoleHint] = {}
        for p in pages:
            if p.has_text_layer:
                continue
            png = doc.render_page_png(p.page_no, dpi=110)
            import base64

            resp = self.client.chat.completions.create(
                model=self.classifier_deployment,
                messages=[
                    {"role": "system", "content": PAGE_CLASSIFIER_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Classify this page."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64," + base64.b64encode(png).decode(),
                                    "detail": "low",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=40,
                temperature=0,
            )
            text = (resp.choices[0].message.content or "").upper()
            role = PageRole.OTHER
            for candidate in ("PO_CONTINUATION", "PACKING_SLIP", "COVER", "TERMS", "BLANK", "PO"):
                if candidate in text:
                    role = PageRole(candidate.lower())
                    break
            rotation = 0
            for deg in (270, 180, 90):
                if str(deg) in text:
                    rotation = deg
                    break
            hints[p.page_no] = PageRoleHint(role=role, rotation=rotation)
        return hints

    # -- main ------------------------------------------------------------- #
    def extract(self, doc: Document, pages: list[PageInfo], page_numbers: list[int]) -> ExtractionResult:
        t0 = time.time()
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._content(doc, pages, page_numbers)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "purchase_order", "schema": self._schema(), "strict": True},
            },
            temperature=0,
        )
        payload = json.loads(resp.choices[0].message.content)
        usage = resp.usage
        price = PRICE_TABLE.get(self.deployment, PRICE_TABLE["gpt-4.1"])
        cost = (
            usage.prompt_tokens / 1_000_000 * price.input_per_1m
            + usage.completion_tokens / 1_000_000 * price.output_per_1m
        )
        return ExtractionResult(
            order=ExtractedOrder.model_validate(payload.get("order", payload)),
            evidence={
                k: Evidence.model_validate(v)
                for k, v in (payload.get("evidence") or {}).items()
                if isinstance(v, dict) and "page" in v
            },
            model_notes=list(payload.get("model_notes") or []),
            handwritten_pages=list(payload.get("handwritten_pages") or []),
            provider="azure-openai",
            model=self.deployment,
            prompt_version=PROMPT_VERSION,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=round(cost, 5),
        )


def _strictify(schema: dict) -> dict:
    """OpenAI strict mode: every property required, no additionalProperties."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


# --------------------------------------------------------------------------- #
# offline: replay recorded model output
# --------------------------------------------------------------------------- #
class FixtureExtractor:
    """Replays a recorded :class:`ExtractionResult` for a sample document."""

    name = "fixture-replay"

    def __init__(self, fixture_dir: str | Path):
        self.dir = Path(fixture_dir)

    def page_roles(self, doc: Document, pages: list[PageInfo]) -> dict[int, PageRoleHint]:
        path = self._path(doc)
        if not path.exists():
            return {}
        raw = json.loads(path.read_text()).get("page_roles") or {}
        out: dict[int, PageRoleHint] = {}
        for k, v in raw.items():
            out[int(k)] = PageRoleHint(
                role=PageRole(v["role"]), rotation=int(v.get("rotation", 0))
            )
        return out

    def _path(self, doc: Document) -> Path:
        return self.dir / (doc.path.stem + ".json")

    def extract(self, doc: Document, pages: list[PageInfo], page_numbers: list[int]) -> ExtractionResult:
        path = self._path(doc)
        if not path.exists():
            raise FileNotFoundError(f"no recorded extraction for {doc.path.name} ({path})")
        raw = json.loads(path.read_text())
        return ExtractionResult.model_validate(raw)
