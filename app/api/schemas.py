from typing import Optional

from pydantic import BaseModel


class CarFilter(BaseModel):
    """Structured filter extracted from the user's natural-language query.

    Every field is optional - only include a value here if it is explicit
    or clearly implied in the query. Do not guess or fill in defaults.
    """

    city: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    run_max: Optional[int] = None
    mark_id: Optional[str] = None
    body_type: Optional[str] = None
    color: Optional[str] = None
    drive_type: Optional[str] = None
    transmission_type: Optional[str] = None
    doors_count: Optional[int] = None
    owners_count_max: Optional[int] = None
    # Explicit numeric ranges the client can state directly ("двигатель не
    # менее 1.6 л", "от 200 л.с.", "минимум 7 мест"). Filtered on the real
    # engine_volume_l / power_hp / seats columns parsed during ETL.
    engine_volume_min: Optional[float] = None
    engine_volume_max: Optional[float] = None
    power_hp_min: Optional[int] = None
    power_hp_max: Optional[int] = None
    seats_min: Optional[int] = None
    # Semantic preferences that map to a deterministic filter over real
    # parsed numbers, not to a made-up field: "семейный" -> seats >= 5,
    # "экономичный" -> small engine (engine_volume_l <= threshold). See
    # app/api/filter_sql.py for the exact thresholds.
    family_friendly: Optional[bool] = None
    economical: Optional[bool] = None
    # "недорогая", "бюджетная", "подешевле" WITHOUT a stated number - unlike
    # price_max (an explicit number from the client), this doesn't invent a
    # cutoff: filter_sql computes it as the real median price of currently
    # matching stock, so it tracks whatever inventory actually has instead
    # of going stale like a hardcoded threshold would.
    prefer_cheap: Optional[bool] = None
    # Leftover fuzzy part of the query that doesn't map to a structured
    # field (e.g. "для дачи с прицепом") - reserved for the optional
    # phase-5 pgvector rerank over description/extras, unused for now.
    free_text_intent: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    # When present, `query` is treated as a follow-up refinement of this
    # filter (from a previous response's parsed_filter) rather than a
    # fresh, from-scratch request - see app.llm.parse_query.refine_query.
    previous_filter: Optional[CarFilter] = None


class Discounts(BaseModel):
    max_discount: float
    tradein_discount: float
    credit_discount: float
    insurance_discount: float


class CarResult(BaseModel):
    id: int
    unique_id: str
    vin: Optional[str]
    mark_id: str
    folder_id: str
    modification_id: Optional[str]
    complectation_name: Optional[str]
    body_type: Optional[str]
    color: Optional[str]
    drive_type: Optional[str]
    transmission_type: Optional[str]
    doors_count: Optional[int]
    engine_volume_l: Optional[float]
    power_hp: Optional[int]
    seats: Optional[int]
    year: int
    run: Optional[int]
    owners_number: Optional[str]
    state: Optional[str]
    custom: Optional[str]
    extras: Optional[str]
    price: float
    currency: Optional[str]
    discounts: Discounts
    price_after_max_discount: float
    city: str
    poi_id: Optional[str]
    contact_phone: Optional[str]
    contact_hours: Optional[str]
    images: list[str]
    video: Optional[str]
    url: Optional[str]
    explanation: str


class SearchResponse(BaseModel):
    parsed_filter: CarFilter
    city_used: Optional[str]
    total_candidates_after_sql_filter: int
    exact_match: bool
    relaxed_fields: list[str]
    results: list[CarResult]


class StatsResponse(BaseModel):
    total_cars: int
    total_models: int
