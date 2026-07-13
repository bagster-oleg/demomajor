from typing import Optional

from pydantic import BaseModel, Field


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
    drive_type: Optional[str] = None
    transmission_type: Optional[str] = None
    doors_count: Optional[int] = None
    owners_count_max: Optional[int] = None
    # Leftover fuzzy part of the query that doesn't map to a structured
    # field (e.g. "для дачи с прицепом") - reserved for the optional
    # phase-5 pgvector rerank over description/extras, unused for now.
    free_text_intent: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=10)


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
    drive_type: Optional[str]
    transmission_type: Optional[str]
    year: int
    run: Optional[int]
    owners_number: Optional[str]
    state: Optional[str]
    price: float
    currency: Optional[str]
    discounts: Discounts
    price_after_max_discount: float
    city: str
    poi_id: Optional[str]
    images: list[str]
    url: Optional[str]
    explanation: str


class SearchResponse(BaseModel):
    parsed_filter: CarFilter
    city_used: Optional[str]
    total_candidates_after_sql_filter: int
    results: list[CarResult]
