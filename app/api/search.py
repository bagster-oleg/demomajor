from sqlalchemy.engine import Connection

from app.api.filter_sql import (
    fetch_candidates,
    fetch_distinct_body_types,
    fetch_distinct_cities,
    fetch_distinct_drive_types,
    fetch_distinct_marks,
    fetch_distinct_transmissions,
)
from app.api.schemas import CarResult, Discounts, SearchRequest, SearchResponse
from app.llm.parse_query import parse_query
from app.llm.rank_explain import rank_and_explain


def _build_car_result(row: dict, explanation: str) -> CarResult:
    price = float(row["price"] or 0)
    max_discount = float(row["max_discount"] or 0)
    return CarResult(
        id=row["id"],
        unique_id=row["unique_id"],
        vin=row["vin"],
        mark_id=row["mark_id"],
        folder_id=row["folder_id"],
        modification_id=row["modification_id"],
        complectation_name=row["complectation_name"],
        body_type=row["body_type"],
        drive_type=row["drive_type"],
        transmission_type=row["transmission_type"],
        year=row["year"],
        run=row["run"],
        owners_number=row["owners_number"],
        state=row["state"],
        price=price,
        currency=row["currency"],
        discounts=Discounts(
            max_discount=max_discount,
            tradein_discount=float(row["tradein_discount"] or 0),
            credit_discount=float(row["credit_discount"] or 0),
            insurance_discount=float(row["insurance_discount"] or 0),
        ),
        price_after_max_discount=price - max_discount,
        city=row["city"],
        poi_id=row["poi_id"],
        images=row["images"] or [],
        url=row["url"],
        explanation=explanation,
    )


def search_cars(conn: Connection, request: SearchRequest) -> SearchResponse:
    known_cities = fetch_distinct_cities(conn)
    known_body_types = fetch_distinct_body_types(conn)
    known_marks = fetch_distinct_marks(conn)
    known_drive_types = fetch_distinct_drive_types(conn)
    known_transmissions = fetch_distinct_transmissions(conn)

    filt = parse_query(
        request.query,
        known_cities=known_cities,
        known_body_types=known_body_types,
        known_marks=known_marks,
        known_drive_types=known_drive_types,
        known_transmissions=known_transmissions,
    )

    # An explicit city selector on the UI always wins over whatever the LLM
    # parsed out of the free-text query.
    if request.city:
        filt.city = request.city

    candidates = fetch_candidates(conn, filt)
    if not candidates:
        return SearchResponse(
            parsed_filter=filt,
            city_used=filt.city,
            total_candidates_after_sql_filter=0,
            results=[],
        )

    ranked = rank_and_explain(request.query, candidates, request.limit)

    candidates_by_id = {c["unique_id"]: c for c in candidates}
    results = []
    for item in ranked:
        row = candidates_by_id.get(item["unique_id"])
        if row is None:
            continue
        results.append(_build_car_result(row, item["explanation"]))

    return SearchResponse(
        parsed_filter=filt,
        city_used=filt.city,
        total_candidates_after_sql_filter=len(candidates),
        results=results,
    )
