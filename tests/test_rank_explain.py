import json
from decimal import Decimal

from app.llm.rank_explain import _compact_candidate


def test_compact_candidate_converts_decimal_to_json_safe_float():
    row = {
        "unique_id": "123",
        "mark_id": "Kia",
        "folder_id": "Rio",
        "modification_id": None,
        "complectation_name": None,
        "body_type": "Седан",
        "drive_type": None,
        "transmission_type": "автомат",
        "year": 2020,
        "run": 50000,
        "owners_number": "Один владелец",
        "state": "Отличное",
        "price": Decimal("950000.00"),
        "currency": "RUR",
        "max_discount": Decimal("60000.00"),
        "tradein_discount": Decimal("0"),
        "credit_discount": Decimal("0"),
        "insurance_discount": Decimal("0"),
        "city": "Москва",
        "poi_id": "где-то",
    }

    compact = _compact_candidate(row)

    # Must not raise - this is what caught the original Decimal bug.
    json.dumps(compact, ensure_ascii=False)
    assert compact["price"] == 950000.0
    assert isinstance(compact["price"], float)
