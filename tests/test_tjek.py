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


def _placed(oid, page, x1, y1, x2, y2):
    url = f"https://img/?u=p.webp&w=600&x1r={x1}&x2r={x2}&y1r={y1}&y2r={y2}&s=abc"
    return {**OFFER, "id": oid, "catalog_page": page, "images": {"view": url}}


def test_offers_get_paper_order():
    # Side 2 står før side 1 i svaret; på side 1 er æg og brød én række,
    # selvom brødet begynder lidt højere oppe end æggene
    items = [
        _placed("side2", 2, 0.0, 0.0, 1.0, 0.5),
        _placed("kaffe", 1, 0.5, 0.5, 1.0, 0.9),
        _placed("brod", 1, 0.5, 0.17, 1.0, 0.53),
        _placed("aeg", 1, 0.0, 0.23, 0.5, 0.49),
        _placed("pasta", 1, 0.0, 0.52, 0.5, 0.85),
        {**OFFER, "id": "uden-side"},
    ]
    offers = tjek.offers_in_paper_order(items, catalog_from_api(CATALOG))
    in_order = sorted(offers, key=lambda o: o.catalog_order)
    assert [o.id for o in in_order] == ["aeg", "brod", "pasta", "kaffe", "side2", "uden-side"]
    assert [o.catalog_page for o in in_order][:5] == [1, 1, 1, 1, 2]


def test_image_box():
    assert tjek.image_box("https://img/?u=x&x1r=0.5&x2r=0.95&y1r=0.56&y2r=0.97") == (0.5, 0.56, 0.95, 0.97)
    assert tjek.image_box("v.jpg") is None and tjek.image_box(None) is None


def test_catalog_url_and_pages(monkeypatch):
    data = {**CATALOG, "dealer": {"markets": [{"slug": "Netto", "country_code": "DK"}]}}
    assert catalog_from_api(data).url == "https://etilbudsavis.dk/Netto?publication=abc123"
    assert catalog_from_api(CATALOG).url is None

    monkeypatch.setattr(TjekSource, "_get", lambda self, path, params: [{"view": "p1.webp"}, {"zoom": "p2.webp"}])
    assert TjekSource().list_pages(catalog_from_api(CATALOG)) == ["p1.webp", "p2.webp"]
