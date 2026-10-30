"""End-to-end behaviour of the pipeline against the four sample documents.

These assertions are the product requirements written as tests: a clean PO must
reach the ERP folder untouched, a fax must never be silently released, and a
missing PO number must block the order.
"""

import csv
import json
import shutil
from pathlib import Path

import pytest

from chronik.matching import ReferenceData
from chronik.pipeline import Settings, run_batch, write_metrics
from chronik.extract import FixtureExtractor
from chronik.review import write_review_pack
from chronik.schema import FlagCode

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    settings = Settings.load(ROOT / "config" / "settings.json")
    results = run_batch(
        SAMPLES,
        SAMPLES / "mail_manifest.json",
        ReferenceData(ROOT / "data" / "erp"),
        FixtureExtractor(ROOT / "fixtures"),
        settings,
        out,
    )
    return {r.assessment.source_filename: r for r in results}, out, results


def _flags(result) -> set[str]:
    return {f.code.value for f in result.assessment.flags}


def test_clean_po_goes_straight_through(run):
    results, out, _ = run
    r = results["clean_po.pdf"]
    assert r.assessment.route == "auto_ready"
    assert _flags(r) == set()
    # one CSV per order, in the drop folder the ERP watches
    assert r.csv_path is not None and r.csv_path.parent == out / "csv"


def test_clean_po_csv_is_exact(run):
    results, _, _ = run
    with open(results["clean_po.pdf"].csv_path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6
    assert {r["ITEM"] for r in rows} == {
        "MD-5521", "MD-5521-NS", "SG-9910", "SG-9910-L", "TS-4410", "IV-2200",
    }
    first = rows[0]
    assert first["PO_NUMBER"] == "NG-4471902"
    assert first["CUSTOMER_ID"] == "C1001"
    assert first["SHIP_TO_ID"] == "S1001-02"
    assert first["QTY"] == "48"
    assert first["UNIT_PRICE"] == "18.40"
    assert first["ORDER_DATE"] == "09/12/2025"
    # the CSV file is CRLF-terminated for the ERP importer
    assert b"\r\n" in results["clean_po.pdf"].csv_path.read_bytes()


def test_fax_is_flagged_not_trusted(run):
    results, _, _ = run
    r = results["fax_multipage.pdf"]
    assert r.assessment.route != "auto_ready"
    flags = _flags(r)
    assert FlagCode.DOC_LOW_QUALITY.value in flags          # scanned page, confidence capped
    assert FlagCode.SHIP_TO_AMBIGUOUS.value in flags        # two near-identical St Aidan addresses
    assert FlagCode.PRICE_MISMATCH.value in flags           # IV-2200 printed above contract
    assert FlagCode.TOTAL_MISMATCH.value in flags           # printed PO total does not add up
    # pages 1 (cover) and 4 (terms) must not be sent to the vision model
    assert [p.page_no for p in r.assessment.pages if p.role.value in ("po", "po_continuation")] == [2, 3]


def test_handwriting_caps_confidence_and_uses_descriptions(run):
    results, _, _ = run
    r = results["handwritten_po.pdf"]
    flags = _flags(r)
    assert FlagCode.HANDWRITTEN.value in flags
    assert FlagCode.ITEM_MATCHED_BY_DESCRIPTION.value in flags
    assert r.assessment.order_confidence <= 0.85
    # every line still resolved to a real SKU - a rep confirms, they do not retype
    assert all(line.sku for line in r.assessment.resolved_lines)


def test_missing_po_number_blocks_and_emits_nothing(run):
    results, out, _ = run
    r = results["unknown_format.pdf"]
    assert r.assessment.route == "blocked"
    assert FlagCode.MISSING_PO_NUMBER.value in _flags(r)
    assert r.csv_path is None
    assert not list((out / "csv").glob("*NO_PO*"))


def test_unmapped_uom_is_flagged_not_translated(run):
    results, _, _ = run
    r = results["unknown_format.pdf"]
    assert FlagCode.UOM_UNMAPPED.value in _flags(r)


def test_evidence_verification_catches_bad_quotes(run):
    results, _, _ = run
    # the recorded model quoted a postal code that is not printed on a text-layer
    # page -> the mechanical check must notice
    assert FlagCode.EVIDENCE_UNVERIFIED.value in _flags(results["unknown_format.pdf"])


def test_metrics_and_review_pack_are_written(run, tmp_path):
    results, out, all_results = run
    metrics = json.loads(write_metrics(all_results, tmp_path).read_text())
    assert metrics["documents"] == 4
    assert metrics["routes"]["auto_ready"] == 1
    assert metrics["routes"]["blocked"] == 1
    assert metrics["model_cost_usd_per_doc"] > 0
    pack = write_review_pack(all_results, SAMPLES, tmp_path / "review")
    html_text = pack.read_text()
    assert "Needs review" in html_text and "Blocked" in html_text
    assert html_text.count("data:image/png;base64") >= 3  # source crops embedded
