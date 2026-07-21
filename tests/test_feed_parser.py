from pathlib import Path

from app.etl.feed_parser import parse_feed_bytes, parse_feed_file

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "feed_msk.xml"


def test_parse_feed_file_returns_all_cars():
    records = parse_feed_file(FIXTURE, city="Москва")
    assert len(records) == 9


def test_parse_feed_sets_city_and_feed_source():
    records = parse_feed_file(FIXTURE, city="Москва")
    for r in records:
        assert r.city == "Москва"
        assert r.feed_source == "feed_msk.xml"


def test_parse_car_fields_and_types():
    records = parse_feed_file(FIXTURE, city="Москва")
    audi = next(r for r in records if r.unique_id == "1937189")

    assert audi.mark_id == "Audi"
    assert audi.folder_id == "A7, II (4K)"
    assert audi.body_type == "Лифтбек"
    assert audi.wheel == "левый"
    assert audi.year == 2021
    assert audi.run == 105036
    assert audi.price == 5100000.0
    assert audi.max_discount == 425000.0
    assert audi.tradein_discount == 150000.0
    assert audi.credit_discount == 275000.0
    assert audi.insurance_discount == 0.0
    assert audi.doors_count == 5
    assert audi.vin == "WAUZZZF22NN004035"
    assert audi.poi_id == "Москва, ул. Маршала Прошлякова, д.13"
    assert audi.url == "https://www.major-expert.ru/cars/1937189/"
    assert len(audi.images) == 29
    assert audi.images[0] == "https://www.major-expert.ru/autoru.php?path=/1937189/1937189_18820919.jpg"


def test_owners_number_kept_raw_and_parsed_to_count():
    records = parse_feed_file(FIXTURE, city="Москва")
    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.owners_number == "Два владельца"
    assert audi.owners_count == 2

    porsche = next(r for r in records if r.unique_id == "1931764")
    assert porsche.owners_number == "Три владельца"
    assert porsche.owners_count == 3


def test_drive_type_derived_from_modification_id():
    records = parse_feed_file(FIXTURE, city="Москва")
    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.modification_id == "55 TFSI 3.0 AMT (340 л.с.) 4WD"
    assert audi.drive_type == "4WD"

    baic = next(r for r in records if r.unique_id == "1945461")
    assert baic.modification_id == "1.5 CVT (105 л.с.)"
    assert baic.drive_type is None


def test_transmission_type_derived_from_modification_id():
    records = parse_feed_file(FIXTURE, city="Москва")
    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.transmission_type == "автомат"  # AMT, grouped with classic automatics

    baic = next(r for r in records if r.unique_id == "1945461")
    assert baic.transmission_type == "автомат"  # CVT

    kia_rio = next(r for r in records if r.unique_id == "1864081")
    assert kia_rio.modification_id == "X-Line 1.4 AT (100 л.с.)"
    assert kia_rio.transmission_type == "автомат"  # AT


def test_engine_volume_power_and_seats_parsed():
    records = parse_feed_file(FIXTURE, city="Москва")

    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.modification_id == "55 TFSI 3.0 AMT (340 л.с.) 4WD"
    assert float(audi.engine_volume_l) == 3.0
    assert audi.power_hp == 340
    assert audi.seats == 4  # Audi A7 has "Количество мест: 4" in extras

    kia_rio = next(r for r in records if r.unique_id == "1864081")
    assert float(kia_rio.engine_volume_l) == 1.4  # "X-Line 1.4 AT (100 л.с.)"
    assert kia_rio.power_hp == 100
    assert kia_rio.seats == 5

    porsche = next(r for r in records if r.unique_id == "1931764")
    assert float(porsche.engine_volume_l) == 2.0  # "2.0 AMT (252 л.с.) 4WD"
    assert porsche.power_hp == 252


def test_contact_info_flattened():
    records = parse_feed_file(FIXTURE, city="Москва")
    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.contact_name == "MAJOR EXPERT"
    assert audi.contact_phone == "74951261388"
    assert audi.contact_hours == "09:00-21:00"


def test_optional_fields_missing_on_some_cars():
    records = parse_feed_file(FIXTURE, city="Москва")
    baic = next(r for r in records if r.unique_id == "1945461")
    assert baic.video is None
    assert baic.complectation_name is None

    kaiyi = next(r for r in records if r.unique_id == "1945413")
    assert kaiyi.complectation_name == "Standard"


def test_fuel_type_defaults_to_petrol_when_no_marker():
    records = parse_feed_file(FIXTURE, city="Москва")
    # None of the fixture cars have a diesel/hybrid/electric marker in
    # modification_id - the feed's implicit default is a petrol engine.
    audi = next(r for r in records if r.unique_id == "1937189")
    assert audi.modification_id == "55 TFSI 3.0 AMT (340 л.с.) 4WD"
    assert audi.fuel_type == "бензин"


def _single_car_xml(modification_id: str) -> bytes:
    return f"""<Data><cars><car>
        <unique_id>1</unique_id>
        <mark_id>Test</mark_id>
        <folder_id>Model</folder_id>
        <modification_id>{modification_id}</modification_id>
    </car></cars></Data>""".encode()


def test_fuel_type_diesel_marker():
    # Regression: "хочу электрокар" surfaced that fuel type had no dedicated
    # field at all - a diesel modification like "3.0d AT..." must resolve
    # to "дизель", not fall through to the petrol default.
    records = parse_feed_bytes(_single_car_xml("3.0d AT (249 л.с.) 4WD"), city="Москва", feed_source="t.xml")
    assert records[0].fuel_type == "дизель"


def test_fuel_type_hybrid_marker():
    records = parse_feed_bytes(_single_car_xml("1.5hyb CVT (190 л.с.)"), city="Москва", feed_source="t.xml")
    assert records[0].fuel_type == "гибрид"


def test_fuel_type_electro_marker():
    # Regression: "хочу электрокар" - a pure-electric modification like
    # "Electro AT (430 кВт) 4WD" has no litre displacement at all, but must
    # still resolve fuel_type to "электро" so it can actually be filtered on.
    records = parse_feed_bytes(_single_car_xml("Electro AT (430 кВт) 4WD"), city="Москва", feed_source="t.xml")
    assert records[0].fuel_type == "электро"
    assert records[0].engine_volume_l is None


def test_parse_feed_bytes_missing_required_field_raises():
    xml = b"""<Data><cars><car>
        <mark_id>KIA</mark_id>
        <folder_id>RIO</folder_id>
    </car></cars></Data>"""
    try:
        parse_feed_bytes(xml, city="Москва", feed_source="broken.xml")
        assert False, "expected ValueError for missing unique_id"
    except ValueError:
        pass
