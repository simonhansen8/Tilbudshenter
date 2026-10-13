import pytest

from tilbudshenter.sources import tjek
from tilbudshenter.sources.tjek import TjekSource, catalog_from_api, offer_from_api

CATALOG = {
    "id": "abc123",
    "label": "Netto uge 42",
    "branding": {"name": "Netto"},
    "dealer_id": "9ba51",
    "run_from": "2026-10-11T00:00:00+0000",
    "run_till": "2026-10-17T23:59:59+0000",
    "offer_count": 2,
}

OFFER = {
    "id": "o1",
    "heading": "Kyllingebryst",
    "description": "Danpo. 900 g",
    "pricing": {"price": 49, "pre_price": 79, "currency": "DKK"},
    "quantity": {
        "unit": {"symbol": "g", "si": {"symbol": "kg", "factor": 0.001}},
        "size": {"from": 900, "to": 900},
        "pieces": {"from": 1, "to": 1},
    },
    "images": {"thumb": "t.jpg", "view": "v.jpg"},
    "run_from": "2026-10-11T00:00:00+0000",
    "run_till": "2026-10-17T23:59:59+0000",
}


def test_catalog_from_api():
    c = catalog_from_api(CATALOG)
    assert (c.id, c.dealer, c.label) == ("abc123", "Netto", "Netto uge 42")
    assert c.run_from.year == 2026 and c.run_till.day == 17


def test_offer_from_api():
    o = offer_from_api(OFFER, catalog_from_api(CATALOG))
    assert o.dealer == "Netto"
    assert o.price == 49 and o.pre_price == 79
    assert o.amount == pytest.approx(0.9) and o.unit == "kg"
    assert o.image_url == "v.jpg"


def test_offer_multipack_and_fallback_quantity():
    catalog = catalog_from_api(CATALOG)
    multipack = {**OFFER, "quantity": {
        "unit": {"symbol": "cl", "si": {"symbol": "l", "factor": 0.01}},
        "size": {"from": 33}, "pieces": {"from": 24},
    }}
    assert offer_from_api(multipack, catalog).amount == pytest.approx(7.92)

    no_quantity = {**OFFER, "quantity": None}
    assert offer_from_api(no_quantity, catalog).amount == pytest.approx(0.9)  # fra beskrivelsen


def test_offer_without_price_is_skipped():
    assert offer_from_api({**OFFER, "pricing": {}}, catalog_from_api(CATALOG)) is None


def test_pagination(monkeypatch):
    monkeypatch.setattr(tjek, "PAGE_SIZE", 2)
    pages = [[{**OFFER, "id": "1"}, {**OFFER, "id": "2"}], [{**OFFER, "id": "3"}]]
    calls = []

    def fake_get(self, path, params):
        calls.append((path, params["offset"]))
        return pages[len(calls) - 1]

    monkeypatch.setattr(TjekSource, "_get", fake_get)
    offers = TjekSource(pause=0).list_offers(catalog_from_api(CATALOG))
    assert [o.id for o in offers] == ["1", "2", "3"]
    assert calls == [("offers", 0), ("offers", 2)]
