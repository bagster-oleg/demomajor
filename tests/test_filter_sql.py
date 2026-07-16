from pathlib import Path

from app.api.filter_sql import fetch_candidates_with_relaxation
from app.api.schemas import CarFilter
from app.etl.feed_parser import parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"


def _seed(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")


def test_exact_match_no_relaxation_needed(conn):
    _seed(conn)
    filt = CarFilter(mark_id="Kia")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert relaxed == []
    assert len(candidates) == 1
    assert candidates[0]["mark_id"] == "Kia"


def test_relaxes_impossible_doors_count_to_find_real_car(conn):
    _seed(conn)
    # No car in the fixture has 3 doors - this must fall back rather than
    # returning nothing, since a real Kia Rio does exist without that
    # constraint.
    filt = CarFilter(mark_id="Kia", doors_count=3)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert relaxed == ["количество дверей"]
    assert len(candidates) == 1
    assert candidates[0]["mark_id"] == "Kia"


def test_relaxes_multiple_fields_in_order(conn):
    _seed(conn)
    # Nothing has drive_type=4WD AND doors_count=3 AND mark_id=Kia (Kia Rio
    # has neither) - both must be dropped before anything turns up.
    filt = CarFilter(mark_id="Kia", doors_count=3, drive_type="4WD")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert set(relaxed) == {"количество дверей", "привод"}
    assert len(candidates) == 1


def test_widens_price_before_dropping_mark(conn):
    _seed(conn)
    # Real Kia Rio price is 650000 with no discount fields relevant here;
    # ask for an unrealistically tight budget just under it so relaxation
    # must widen price rather than immediately dropping the brand.
    filt = CarFilter(mark_id="Kia", price_max=100)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert "бюджет" in relaxed
    # Even widened by 20%, 100 * 1.2 is still nowhere near 650000, so this
    # must have gone all the way to dropping the brand too.
    assert "марка" in relaxed
    assert len(candidates) >= 1


def test_never_relaxes_city_even_when_nothing_matches(conn):
    _seed(conn)
    filt = CarFilter(city="Владивосток")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert candidates == []
    assert exact_match is False
    # city isn't one of the relaxable fields - confirms it was never touched,
    # not just coincidentally absent from the (empty) relaxed list.
    assert "город" not in relaxed


def test_relaxation_never_returns_duplicate_labels(conn):
    _seed(conn)
    # year_min and year_max both map to the same human label - must be
    # deduped rather than shown twice.
    filt = CarFilter(mark_id="Kia", year_min=2025, year_max=2025, doors_count=3)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert len(relaxed) == len(set(relaxed))


def test_economical_filters_to_small_engine(conn):
    _seed(conn)
    # economical -> engine_volume_l <= 1.6. Fixture engines: 3.0 (Audi),
    # 1.5, 1.6, 1.5, 1.5, 1.4, 2.0, 2.0, 2.0. So <=1.6 keeps exactly the
    # 1.4/1.5/1.6 ones and excludes the 2.0s and the 3.0.
    filt = CarFilter(economical=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) > 0
    assert all(float(c["engine_volume_l"]) <= 1.6 for c in candidates)


def test_family_friendly_filters_to_five_plus_seats(conn):
    _seed(conn)
    # family_friendly -> seats >= 5. The Audi A7 (4 seats) must be excluded.
    filt = CarFilter(family_friendly=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert all(c["seats"] >= 5 for c in candidates)
    assert "1937189" not in {c["unique_id"] for c in candidates}  # Audi A7, 4 seats


def test_family_and_economical_compose(conn):
    _seed(conn)
    filt = CarFilter(family_friendly=True, economical=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert all(c["seats"] >= 5 and float(c["engine_volume_l"]) <= 1.6 for c in candidates)


def test_color_and_engine_volume_min_compose(conn):
    # Regression: "авто белого цвета с двигателем не менее 1.6 литра" used
    # to return all 9 cars (any color, any engine) because CarFilter had no
    # field for either color or an explicit engine range - both got lost
    # in free_text_intent, which only reranks, never filters.
    _seed(conn)
    filt = CarFilter(color="Белый", engine_volume_min=1.6)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 2  # the two white Nissan Qashqai, both 2.0L
    assert all(c["color"] == "Белый" for c in candidates)
    assert all(float(c["engine_volume_l"]) >= 1.6 for c in candidates)


def test_color_excludes_other_colors(conn):
    _seed(conn)
    filt = CarFilter(color="Синий")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 2  # Porsche Macan + Kia Rio, both "Синий"
    assert all(c["color"] == "Синий" for c in candidates)


def test_engine_volume_max_excludes_bigger_engines(conn):
    _seed(conn)
    filt = CarFilter(engine_volume_max=1.5)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert all(float(c["engine_volume_l"]) <= 1.5 for c in candidates)
    assert "1937189" not in {c["unique_id"] for c in candidates}  # Audi, 3.0L


def test_prefer_cheap_excludes_the_expensive_half_of_stock(conn):
    _seed(conn)
    # Regression: "недорогая первая машина для сына" with no stated number
    # used to return all 9 cars, Porsche Macan (3.77M) and Audi A7 (5.1M)
    # included, because there was no field for "cheap without a number" to
    # land on at all. prefer_cheap must cap it at the real median price of
    # current stock instead.
    filt = CarFilter(prefer_cheap=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    prices = {float(c["price"]) for c in candidates}
    assert 5_100_000.0 not in prices  # Audi A7
    assert 3_770_000.0 not in prices  # Porsche Macan
    assert 650_000.0 in prices  # Kia Rio - the actual cheapest car in stock


def test_prefer_cheap_orders_cheapest_first(conn):
    _seed(conn)
    filt = CarFilter(prefer_cheap=True)
    candidates, _exact_match, _relaxed = fetch_candidates_with_relaxation(conn, filt)
    prices = [float(c["price"]) for c in candidates]
    assert prices == sorted(prices)


def test_prefer_cheap_ignored_when_explicit_price_max_given(conn):
    _seed(conn)
    # An explicit number always wins - prefer_cheap only kicks in when the
    # client didn't state a number at all.
    filt = CarFilter(prefer_cheap=True, price_max=5_000_000)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    prices = {float(c["price"]) for c in candidates}
    assert 3_770_000.0 in prices  # Porsche Macan - under the explicit 5M cap
