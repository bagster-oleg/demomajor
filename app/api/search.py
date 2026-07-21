import logging

from sqlalchemy.engine import Connection

from app.api.filter_sql import (
    DEFAULT_CANDIDATE_LIMIT,
    FUZZY_RERANK_POOL_LIMIT,
    fetch_candidates_with_relaxation,
    fetch_distinct_body_types,
    fetch_distinct_cities,
    fetch_distinct_colors,
    fetch_distinct_drive_types,
    fetch_distinct_fuel_types,
    fetch_distinct_marks,
    fetch_distinct_transmissions,
)
from app.api.schemas import CarResult, Discounts, SearchRequest, SearchResponse
from app.llm.parse_query import parse_query, refine_query
from app.llm.rank_explain import rank_and_explain
from app.vector.rerank import rerank_by_free_text_intent

logger = logging.getLogger(__name__)

# Safety valve for the rank/explain LLM call - not a business "top N", just
# a bound on how many cars get sent through one prompt. Every candidate up
# to this count gets explained; none are chosen/dropped as "not good enough".
MAX_EXPLAINED_CANDIDATES = 15


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
        color=row["color"],
        drive_type=row["drive_type"],
        transmission_type=row["transmission_type"],
        fuel_type=row["fuel_type"],
        doors_count=row["doors_count"],
        engine_volume_l=float(row["engine_volume_l"]) if row["engine_volume_l"] is not None else None,
        power_hp=row["power_hp"],
        seats=row["seats"],
        year=row["year"],
        run=row["run"],
        owners_number=row["owners_number"],
        state=row["state"],
        custom=row["custom"],
        not_registered_in_russia=row["not_registered_in_russia"],
        extras=row["extras"],
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
        contact_phone=row["contact_phone"],
        contact_hours=row["contact_hours"],
        images=row["images"] or [],
        video=row["video"],
        url=row["url"],
        explanation=explanation,
    )


def search_cars(conn: Connection, request: SearchRequest) -> SearchResponse:
    known_cities = fetch_distinct_cities(conn)
    known_body_types = fetch_distinct_body_types(conn)
    known_marks = fetch_distinct_marks(conn)
    known_drive_types = fetch_distinct_drive_types(conn)
    known_transmissions = fetch_distinct_transmissions(conn)
    known_colors = fetch_distinct_colors(conn)
    known_fuel_types = fetch_distinct_fuel_types(conn)

    if request.previous_filter is not None:
        # Follow-up refinement ("а подешевле?") - update the existing
        # filter instead of re-parsing the whole conversation from scratch.
        filt, dropped_fields = refine_query(
            request.previous_filter,
            request.query,
            known_cities=known_cities,
            known_body_types=known_body_types,
            known_marks=known_marks,
            known_drive_types=known_drive_types,
            known_transmissions=known_transmissions,
            known_colors=known_colors,
            known_fuel_types=known_fuel_types,
        )
    else:
        filt, dropped_fields = parse_query(
            request.query,
            known_cities=known_cities,
            known_body_types=known_body_types,
            known_marks=known_marks,
            known_drive_types=known_drive_types,
            known_transmissions=known_transmissions,
            known_colors=known_colors,
            known_fuel_types=known_fuel_types,
        )

    # An explicit city selector on the UI always wins over whatever the LLM
    # parsed out of the free-text query - so a city dropped by the clamp
    # (the model named a city with no stock) is moot once the UI supplies
    # a real one.
    if request.city:
        filt.city = request.city
        dropped_fields = [f for f in dropped_fields if f != "город"]

    # If free_text_intent is set, the embedding rerank below needs a much
    # bigger pool to actually work with - the SQL ORDER BY is only a crude
    # price/discount/year heuristic, so truncating to the small default
    # limit here would mean a genuinely better semantic match ranked 31st+
    # by that heuristic never even reaches the rerank step.
    pool_limit = FUZZY_RERANK_POOL_LIMIT if filt.free_text_intent else DEFAULT_CANDIDATE_LIMIT

    # If nothing matches the filter exactly, this deterministically loosens
    # it (cheapest constraints first) until something in stock does, rather
    # than just returning "no results" - real cars, never invented ones,
    # with an honest account of what had to give.
    candidates, sql_exact_match, relaxed_fields = fetch_candidates_with_relaxation(
        conn, filt, limit=pool_limit
    )

    # A field the clamp step silently dropped (e.g. mark_id="Mercedes" - no
    # Mercedes in stock, so it never became a SQL condition at all) must
    # count as "not an exact match" too - otherwise a query like "мерседес
    # джип" can come back reporting a perfect match just because the SQL
    # step, having lost the brand, still found SUVs.
    exact_match = sql_exact_match and not dropped_fields
    all_relaxed_fields = list(dict.fromkeys(dropped_fields + relaxed_fields))

    # Cheap, low-cardinality gap-finding: log the query alongside what it
    # actually parsed to and how well it matched, so real usage patterns
    # (not just the ones we happened to test by hand) surface gaps between
    # the pitch and actual behavior. No PII beyond the query text itself.
    logger.info(
        "search query=%r parsed_filter=%s exact_match=%s relaxed_fields=%s n_candidates=%d",
        request.query,
        filt.model_dump(exclude_none=True),
        exact_match,
        all_relaxed_fields,
        len(candidates),
    )

    if not candidates:
        return SearchResponse(
            parsed_filter=filt,
            city_used=filt.city,
            total_candidates_after_sql_filter=0,
            exact_match=exact_match,
            relaxed_fields=all_relaxed_fields,
            results=[],
        )

    # Phase-5 rerank: reorders the SQL-filtered candidates by similarity to
    # whatever fuzzy leftover the query-parsing step couldn't map to a real
    # column (e.g. "для дачи с прицепом") - on top of the SQL filter, never
    # instead of it, and never dropping a candidate.
    candidates = rerank_by_free_text_intent(filt.free_text_intent, candidates)

    ranked = rank_and_explain(
        request.query, candidates[:MAX_EXPLAINED_CANDIDATES], all_relaxed_fields
    )

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
        exact_match=exact_match,
        relaxed_fields=all_relaxed_fields,
        results=results,
    )
