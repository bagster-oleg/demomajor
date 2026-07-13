"""Parse Major Auto / Auto.ru-format XML car feeds into CarRecord models.

One feed file corresponds to one city; the caller supplies the city name
(from the FEED_SOURCES config), since the feed itself does not carry it.

Real feed quirks handled here (observed in fixtures/feed_msk.xml):
- Root is <Data><cars><car>...</car></cars></Data> (nesting varies), so we
  search for `car` nodes anywhere under the root rather than assuming a
  fixed parent.
- `owners_number` is a Russian phrase ("Два владельца"), not a number - we
  keep the raw phrase and additionally derive an integer count where
  possible.
- There is no dedicated "привод" (drive type) field. We derive a best-effort
  `drive_type` from the `4WD` marker commonly present in `modification_id`.
- `poi_id` is actually a full showroom address string, not an opaque id.
- Optional fields (`video`, `complectation_name`) are not present on every
  car node.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lxml import etree
from pydantic import BaseModel

_OWNERS_WORD_TO_COUNT = {
    "один": 1,
    "два": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
}


class CarRecord(BaseModel):
    city: str
    unique_id: str
    vin: Optional[str] = None
    mark_id: str
    folder_id: str
    modification_id: Optional[str] = None
    complectation_name: Optional[str] = None
    body_type: Optional[str] = None
    wheel: Optional[str] = None
    color: Optional[str] = None
    metallic: Optional[str] = None
    availability: Optional[str] = None
    custom: Optional[str] = None
    state: Optional[str] = None
    owners_number: Optional[str] = None
    owners_count: Optional[int] = None
    not_registered_in_russia: Optional[bool] = None
    run: Optional[int] = None
    year: Optional[int] = None
    registry_year: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    max_discount: Optional[float] = None
    tradein_discount: Optional[float] = None
    credit_discount: Optional[float] = None
    insurance_discount: Optional[float] = None
    doors_count: Optional[int] = None
    drive_type: Optional[str] = None
    transmission_type: Optional[str] = None
    description: Optional[str] = None
    extras: Optional[str] = None
    images: list[str] = []
    video: Optional[str] = None
    poi_id: Optional[str] = None
    pts: Optional[str] = None
    sts: Optional[str] = None
    action: Optional[str] = None
    exchange: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_hours: Optional[str] = None
    online_view_available: Optional[bool] = None
    with_nds: Optional[bool] = None
    url: Optional[str] = None
    feed_source: str
    raw: dict


def _text(node: etree._Element, tag: str) -> Optional[str]:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _int(node: etree._Element, tag: str) -> Optional[int]:
    value = _text(node, tag)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(node: etree._Element, tag: str) -> Optional[float]:
    value = _text(node, tag)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool(node: etree._Element, tag: str) -> Optional[bool]:
    value = _text(node, tag)
    if value is None:
        return None
    return value.strip().lower() == "true"


def _images(node: etree._Element) -> list[str]:
    images_node = node.find("images")
    if images_node is None:
        return []
    return [img.text.strip() for img in images_node.findall("image") if img.text and img.text.strip()]


def _owners_count(owners_text: Optional[str]) -> Optional[int]:
    if not owners_text:
        return None
    digits = re.search(r"\d+", owners_text)
    if digits:
        return int(digits.group())
    for word, count in _OWNERS_WORD_TO_COUNT.items():
        if word in owners_text.lower():
            return count
    return None


def _drive_type(modification_id: Optional[str]) -> Optional[str]:
    """Best-effort drive-type guess: the feed has no dedicated field for it,
    so we look for the common 4WD marker inside modification_id. Anything
    else is left unset rather than guessed."""
    if not modification_id:
        return None
    if re.search(r"\b4WD\b", modification_id, re.IGNORECASE):
        return "4WD"
    if re.search(r"\bAWD\b", modification_id, re.IGNORECASE):
        return "AWD"
    return None


_TRANSMISSION_TOKEN_RE = re.compile(r"\b(AMT|CVT|DSG|AT|MT)\b", re.IGNORECASE)
_TRANSMISSION_TO_LABEL = {
    "AT": "автомат",
    "CVT": "автомат",
    # AMT/DSG are technically robotized/dual-clutch gearboxes, not a classic
    # torque-converter automatic, but buyers colloquially call anything
    # without a clutch pedal "автомат" - grouping them keeps search results
    # matching how people actually phrase queries ("нужен автомат").
    "AMT": "автомат",
    "DSG": "автомат",
    "MT": "механика",
}


def _transmission_type(modification_id: Optional[str]) -> Optional[str]:
    """Best-effort transmission guess: also not a dedicated field, derived
    from the gearbox token embedded in modification_id (e.g. "... AMT ...",
    "... CVT ...")."""
    if not modification_id:
        return None
    match = _TRANSMISSION_TOKEN_RE.search(modification_id)
    if not match:
        return None
    return _TRANSMISSION_TO_LABEL[match.group(1).upper()]


def _contact(node: etree._Element) -> tuple[Optional[str], Optional[str], Optional[str]]:
    contact_info = node.find("contact_info")
    if contact_info is None:
        return None, None, None
    contact = contact_info.find("contact")
    if contact is None:
        return None, None, None
    return _text(contact, "name"), _text(contact, "phone"), _text(contact, "time")


def _node_to_dict(node: etree._Element) -> dict:
    result: dict = {}
    for child in node:
        if len(child):
            result[child.tag] = [_node_to_dict(c) if len(c) else (c.text or "") for c in child]
        else:
            result[child.tag] = child.text
    return result


def parse_car_node(node: etree._Element, city: str, feed_source: str) -> CarRecord:
    unique_id = _text(node, "unique_id")
    mark_id = _text(node, "mark_id")
    folder_id = _text(node, "folder_id")
    if not unique_id or not mark_id or not folder_id:
        raise ValueError(
            f"car node missing required field(s) unique_id/mark_id/folder_id in {feed_source}"
        )

    modification_id = _text(node, "modification_id")
    owners_number = _text(node, "owners_number")
    contact_name, contact_phone, contact_hours = _contact(node)

    return CarRecord(
        city=city,
        unique_id=unique_id,
        vin=_text(node, "vin"),
        mark_id=mark_id,
        folder_id=folder_id,
        modification_id=modification_id,
        complectation_name=_text(node, "complectation_name"),
        body_type=_text(node, "body_type"),
        wheel=_text(node, "wheel"),
        color=_text(node, "color"),
        metallic=_text(node, "metallic"),
        availability=_text(node, "availability"),
        custom=_text(node, "custom"),
        state=_text(node, "state"),
        owners_number=owners_number,
        owners_count=_owners_count(owners_number),
        not_registered_in_russia=_bool(node, "not_registered_in_russia"),
        run=_int(node, "run"),
        year=_int(node, "year"),
        registry_year=_int(node, "registry_year"),
        price=_float(node, "price"),
        currency=_text(node, "currency"),
        max_discount=_float(node, "max_discount"),
        tradein_discount=_float(node, "tradein_discount"),
        credit_discount=_float(node, "credit_discount"),
        insurance_discount=_float(node, "insurance_discount"),
        doors_count=_int(node, "doors_count"),
        drive_type=_drive_type(modification_id),
        transmission_type=_transmission_type(modification_id),
        description=_text(node, "description"),
        extras=_text(node, "extras"),
        images=_images(node),
        video=_text(node, "video"),
        poi_id=_text(node, "poi_id"),
        pts=_text(node, "pts"),
        sts=_text(node, "sts"),
        action=_text(node, "action"),
        exchange=_text(node, "exchange"),
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_hours=contact_hours,
        online_view_available=_bool(node, "online_view_available"),
        with_nds=_bool(node, "with_nds"),
        url=_text(node, "url"),
        feed_source=feed_source,
        raw=_node_to_dict(node),
    )


def parse_feed_bytes(xml_bytes: bytes, city: str, feed_source: str) -> list[CarRecord]:
    root = etree.fromstring(xml_bytes)
    return [parse_car_node(car_node, city, feed_source) for car_node in root.findall(".//car")]


def parse_feed_file(path: str | Path, city: str) -> list[CarRecord]:
    path = Path(path)
    return parse_feed_bytes(path.read_bytes(), city=city, feed_source=path.name)
