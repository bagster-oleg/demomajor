from datetime import datetime, timezone
from pathlib import Path

from app.api.filter_sql import fetch_candidates_with_relaxation
from app.api.schemas import CarFilter
from app.etl.feed_parser import parse_feed_bytes, parse_feed_file
from app.etl.upsert import sync_city_feed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"


def _seed(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    sync_city_feed(conn, records, city="Москва")


_ELECTRIC_CAR_XML = """<Data><cars><car>
    <unique_id>9999001</unique_id>
    <mark_id>Voyah</mark_id>
    <folder_id>Dream, I</folder_id>
    <modification_id>108.7 kWh Electro AT (320 кВт) 4WD</modification_id>
    <body_type>Внедорожник 5 дв.</body_type>
    <price>4600000</price>
    <year>2024</year>
    <extras>Количество мест: 7</extras>
</car></cars></Data>""".encode()


def _seed_with_electric_car(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    records += parse_feed_bytes(_ELECTRIC_CAR_XML, city="Москва", feed_source="electric.xml")
    sync_city_feed(conn, records, city="Москва")


_LOW_MILEAGE_IMPORT_XML = """<Data><cars><car>
    <unique_id>9999002</unique_id>
    <mark_id>Toyota</mark_id>
    <folder_id>Land Cruiser</folder_id>
    <modification_id>4.0 AT (249 л.с.) 4WD</modification_id>
    <body_type>Внедорожник 5 дв.</body_type>
    <price>7500000</price>
    <year>2023</year>
    <run>5000</run>
    <not_registered_in_russia>true</not_registered_in_russia>
</car></cars></Data>""".encode()


def _seed_with_low_mileage_import_car(conn):
    records = parse_feed_file(FIXTURE, city="Москва")
    records += parse_feed_bytes(_LOW_MILEAGE_IMPORT_XML, city="Москва", feed_source="import.xml")
    sync_city_feed(conn, records, city="Москва")


def test_exact_match_no_relaxation_needed(conn):
    _seed(conn)
    filt = CarFilter(mark_ids=["Kia"])
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
    filt = CarFilter(mark_ids=["Kia"], doors_count=3)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert relaxed == ["количество дверей"]
    assert len(candidates) == 1
    assert candidates[0]["mark_id"] == "Kia"


def test_relaxes_multiple_fields_in_order(conn):
    _seed(conn)
    # Nothing has drive_type=4WD AND doors_count=3 AND mark_id=Kia (Kia Rio
    # has neither) - both must be dropped before anything turns up.
    filt = CarFilter(mark_ids=["Kia"], doors_count=3, drive_type="4WD")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert set(relaxed) == {"количество дверей", "привод"}
    assert len(candidates) == 1


def test_widens_price_before_dropping_mark(conn):
    _seed(conn)
    # Real Kia Rio price is 650000 with no discount fields relevant here;
    # ask for an unrealistically tight budget just under it so relaxation
    # must widen price rather than immediately dropping the brand.
    filt = CarFilter(mark_ids=["Kia"], price_max=100)
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
    filt = CarFilter(mark_ids=["Kia"], year_min=2025, year_max=2025, doors_count=3)
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


def test_fuel_type_filters_to_electric_only(conn):
    # Regression: "хочу электрокар но семейная вместительная" used to
    # return Cadillac/Rolls-Royce/BMW petrol-diesel giants because fuel
    # type had no dedicated field at all - only free_text_intent, which
    # never filters. fuel_type="электро" must exclude every petrol/diesel
    # car in the fixture and keep only the real electric one.
    _seed_with_electric_car(conn)
    filt = CarFilter(fuel_type="электро")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["mark_id"] == "Voyah"
    assert candidates[0]["fuel_type"] == "электро"


def test_fuel_type_and_family_friendly_compose(conn):
    # The actual reported scenario: electric AND family/spacious (5+ seats).
    _seed_with_electric_car(conn)
    filt = CarFilter(fuel_type="электро", family_friendly=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["seats"] == 7


def test_fuel_type_petrol_excludes_the_electric_car(conn):
    _seed_with_electric_car(conn)
    filt = CarFilter(fuel_type="бензин")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert "9999001" not in {c["unique_id"] for c in candidates}


def test_mark_ids_or_matches_either_brand(conn):
    # "Kia или Porsche" - a known gap discussed earlier: mark_id used to
    # accept only one value at a time.
    _seed(conn)
    filt = CarFilter(mark_ids=["Kia", "Porsche"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert {c["mark_id"] for c in candidates} == {"Kia", "Porsche"}


def test_mark_ids_single_value_still_works_like_old_mark_id(conn):
    _seed(conn)
    filt = CarFilter(mark_ids=["Kia"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["mark_id"] == "Kia"


def test_exclude_colors_removes_matching_cars(conn):
    # "любой цвет кроме белого" - the two white Nissans must be excluded,
    # everything else stays.
    _seed(conn)
    filt = CarFilter(exclude_colors=["Белый"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 7
    assert all(c["color"] != "Белый" for c in candidates)


def test_exclude_body_types_removes_matching_cars(conn):
    # "не хочу внедорожник" - 5 of the 9 fixture cars are "Внедорожник 5 дв."
    _seed(conn)
    filt = CarFilter(exclude_body_types=["Внедорожник 5 дв."])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 4
    assert all(c["body_type"] != "Внедорожник 5 дв." for c in candidates)


def test_required_features_single_match(conn):
    # Only the EXEED has a panoramic roof in the fixture.
    _seed(conn)
    filt = CarFilter(required_features=["панорамная крыша"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["unique_id"] == "1862622"


def test_required_features_are_anded_together(conn):
    # Regression target: "хочу панорамную крышу и навигацию" must require
    # BOTH, not either - only the EXEED has both in the fixture.
    _seed(conn)
    filt = CarFilter(required_features=["панорамная крыша", "навигация"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["unique_id"] == "1862622"


def test_required_features_excludes_cars_missing_the_option(conn):
    # Porsche Macan has no cruise control in the fixture - must be excluded
    # when the client explicitly asks for it.
    _seed(conn)
    filt = CarFilter(required_features=["круиз-контроль"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert "1931764" not in {c["unique_id"] for c in candidates}


def test_prefer_premium_excludes_the_cheap_half_of_stock(conn):
    # Symmetric opposite of prefer_cheap: "топовая комплектация"/"подороже"
    # with no stated number must exclude cheap cars, not include everything.
    _seed(conn)
    filt = CarFilter(prefer_premium=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    prices = {float(c["price"]) for c in candidates}
    assert 650_000.0 not in prices  # Kia Rio - the cheapest car in stock
    assert 5_100_000.0 in prices  # Audi A7 stays in the premium half


def test_prefer_premium_orders_priciest_first(conn):
    _seed(conn)
    filt = CarFilter(prefer_premium=True)
    candidates, _exact_match, _relaxed = fetch_candidates_with_relaxation(conn, filt)
    prices = [float(c["price"]) for c in candidates]
    assert prices == sorted(prices, reverse=True)


def test_prefer_premium_ignored_when_explicit_price_min_given(conn):
    _seed(conn)
    filt = CarFilter(prefer_premium=True, price_min=500_000)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    prices = {float(c["price"]) for c in candidates}
    assert 650_000.0 in prices  # Kia Rio - not excluded, price_min already satisfies it


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


def test_exclude_mark_ids_removes_matching_brand(conn):
    # "не хочу BMW" (here: не хочу Kia) - the rest of the fixture stays.
    _seed(conn)
    filt = CarFilter(exclude_mark_ids=["Kia"])
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 8
    assert "Kia" not in {c["mark_id"] for c in candidates}


def test_recent_only_filters_to_recent_model_years(conn):
    # "новая машина" without a stated year - only cars within the last
    # RECENT_MAX_AGE_YEARS of the real current year should match.
    _seed(conn)
    current_year = datetime.now(timezone.utc).year
    filt = CarFilter(recent_only=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert all(c["year"] >= current_year - 2 for c in candidates)


def test_low_mileage_filters_to_real_low_mileage_car(conn):
    # Every fixture car has 75k+ km - only the synthetic 5k-km import
    # should match "почти не ездили" without a stated number.
    _seed_with_low_mileage_import_car(conn)
    filt = CarFilter(low_mileage=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["unique_id"] == "9999002"


def test_not_registered_in_russia_filters_to_real_import(conn):
    _seed_with_low_mileage_import_car(conn)
    filt = CarFilter(not_registered_in_russia=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["unique_id"] == "9999002"


def test_not_registered_in_russia_false_excludes_the_import(conn):
    _seed_with_low_mileage_import_car(conn)
    filt = CarFilter(not_registered_in_russia=False)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert "9999002" not in {c["unique_id"] for c in candidates}


def test_complectation_keyword_matches_named_trim(conn):
    # Real fixture data: Kaiyi has complectation_name "Standard", Kia Rio
    # has "Comfort" - a raw substring match, not a clamped enum (too many
    # distinct real trim names across brands to enumerate).
    _seed(conn)
    filt = CarFilter(complectation_keyword="Standard")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert len(candidates) == 1
    assert candidates[0]["unique_id"] == "1945413"


def test_complectation_keyword_no_match_relaxes_honestly(conn):
    _seed(conn)
    filt = CarFilter(complectation_keyword="Nonexistent Trim Name")
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is False
    assert "комплектация" in relaxed
    assert len(candidates) > 0


def test_safety_equipped_filters_to_full_safety_kit(conn):
    # Regression: "недорогую и безопасную" surfaced that "безопасная" had
    # no real home at all - it only landed in free_text_intent (fuzzy
    # rerank, never a filter), so prefer_cheap alone decided the results
    # and pulled in the cheapest cars regardless of actual safety
    # equipment. safety_equipped requires ESP + both side and curtain
    # airbags - real fixture data: only EXEED and both Nissans and the
    # Porsche have all three; the rest have ESP alone at most.
    _seed(conn)
    filt = CarFilter(safety_equipped=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    assert {c["unique_id"] for c in candidates} == {"1862622", "1946052", "1937389", "1931764"}


def test_safety_equipped_and_prefer_cheap_compose(conn):
    # The actual reported scenario: cheap AND safety-equipped together.
    _seed(conn)
    filt = CarFilter(safety_equipped=True, prefer_cheap=True)
    candidates, exact_match, relaxed = fetch_candidates_with_relaxation(conn, filt)
    assert exact_match is True
    ids = {c["unique_id"] for c in candidates}
    assert ids.issubset({"1862622", "1946052", "1937389", "1931764"})
