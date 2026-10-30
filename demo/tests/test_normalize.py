from datetime import date
from decimal import Decimal

from chronik.normalize import (
    canonical_uom,
    normalize_street,
    normalize_text,
    normalize_zip,
    parse_date,
    sku_key,
)


def test_uom_mapping_is_explicit_and_never_guesses():
    assert canonical_uom("boxes") == ("BX", True)
    assert canonical_uom("CASE") == ("CS", True)
    assert canonical_uom("cs.") == ("CS", True)
    # unknown words come back mapped=False so the pipeline flags instead of guessing
    assert canonical_uom("dispenser") == ("DIS", False)
    assert canonical_uom(None) == (None, False)


def test_sku_key_strips_everything_people_type_wrong():
    assert sku_key("NG-10042") == sku_key("ng 10042") == "NG10042"
    assert sku_key("12/345.A") == "12345A"
    assert sku_key(None) == ""


def test_date_ambiguity_is_reported():
    d, ambiguous = parse_date("03/04/2025")
    assert d == date(2025, 3, 4) and ambiguous is True
    d, ambiguous = parse_date("2025-09-12")
    assert d == date(2025, 9, 12) and ambiguous is False
    assert parse_date("not a date") == (None, False)


def test_text_and_address_normalisation():
    assert normalize_text("Northgate Surgical Supply, LLC.") == "NORTHGATE SURGICAL SUPPLY"
    assert normalize_street("900 Beacon Street").startswith("900 BEACON ST")
    assert normalize_zip("62704-1234") == "62704"
    assert Decimal("18.40") == Decimal("18.40")
