from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.filter_sql import fetch_distinct_cities, fetch_stats
from app.api.schemas import SearchRequest, SearchResponse, StatsResponse
from app.api.search import search_cars
from app.db.session import engine

app = FastAPI(title="Major Auto — подбор авто")

# Demo only: the frontend is a separate Vite dev server on another port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/cities")
def cities() -> list[str]:
    with engine.connect() as conn:
        return fetch_distinct_cities(conn)


@app.get("/api/stats", response_model=StatsResponse)
def stats(city: Optional[str] = None) -> StatsResponse:
    with engine.connect() as conn:
        return StatsResponse(**fetch_stats(conn, city))


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    with engine.connect() as conn:
        return search_cars(conn, request)
