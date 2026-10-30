from pathlib import Path

from chronik.matching import ReferenceData
from chronik.schema import Party

DATA = Path(__file__).resolve().parent.parent / "data" / "erp"


def ref() -> ReferenceData:
    return ReferenceData(DATA)


def test_sender_domain_wins_over_printed_name():
    r = ref()
    cid, score, method, rivals = r.match_customer(
        "purchasing@northgatesurgical.example", "Some Other Name", Party(name="Some Other Name")
    )
    assert cid == "C1001" and method == "sender_domain" and not rivals


def test_two_similar_customers_are_never_silently_picked():
    r = ref()
    cid, score, method, rivals = r.match_customer(
        "someone@unknown.example", "Northgate", Party(name="Northgate")
    )
    # "Northgate" matches both C1001 and C1005 aliases -> ambiguous, not a guess
    assert cid is None
    assert method == "name_ambiguous"
    assert "C1001" in rivals and "C1005" in rivals


def test_ship_to_search_is_scoped_to_the_matched_customer():
    r = ref()
    # the St Aidan address exists only under C1002; asking as C1001 must not find it
    aidan = Party(street="77 Prospect Ave", city="Milwaukee", state="WI", zip="53211")
    cid, score, *_ = r.match_ship_to("C1002", aidan)
    assert cid.startswith("S1002") and score >= 90
    # We still return the closest address so the review sheet can show it, but
    # the score must sit far below the auto-accept threshold.
    _nearest, score2, *_ = r.match_ship_to("C1001", aidan)
    assert score2 < 76


def test_crosswalk_beats_description_and_is_customer_scoped():
    r = ref()
    hit = r.match_item("C1002", "LV-GZ44", None)
    assert hit["sku"] == "MD-5521" and hit["method"] == "customer_part"
    # same part number under a different customer must not match
    miss = r.match_item("C1001", "LV-GZ44", None)
    assert miss["sku"] is None


def test_legacy_part_numbers_are_global():
    r = ref()
    hit = r.match_item("C9999", "10021", None)
    assert hit["sku"] == "SG-9910" and hit["method"] == "legacy_part"


def test_inactive_items_are_not_offered_by_description():
    r = ref()
    hit = r.match_item("C1004", "B4", None)
    # B4 is not in the crosswalk; the description of the iodine item is inactive
    assert hit["sku"] is None
