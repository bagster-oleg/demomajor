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
