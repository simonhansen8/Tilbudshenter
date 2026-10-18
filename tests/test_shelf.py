"""Normalpriser fra REMA 1000's webshop til madplanens basispriser.

tests/data/rema_sample.json er et udsnit af det rigtige sortiment.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tilbudshenter import shelf
from tilbudshenter.mealplan import NORMAL_PRICES, basis_price, plan_payload
from tilbudshenter.sources import rema
from tilbudshenter.sources.base import SourceError
from tilbudshenter.sources.rema import ShelfPrice, shelf_price

SAMPLE = [ShelfPrice.from_dict(p) for p in
          json.loads((Path(__file__).parent / "data" / "rema_sample.json").read_text(encoding="utf-8"))]


def test_shelf_price_skips_campaign_only():
    product = {"name": "MÆLK", "underline": "1 LTR.", "department": {"name": "Mejeri"},
               "prices": [{"price": 8.0, "is_campaign": True, "compare_unit": "ltr", "compare_unit_price": 8.0}]}
    assert shelf_price(product) is None
    product["prices"].append({"price": 10.95, "is_campaign": False, "compare_unit": "ltr", "compare_unit_price": 10.95})
    p = shelf_price(product)
    assert (p.price, p.unit, p.unit_price, p.department) == (10.95, "l", 10.95, "Mejeri")


def test_basis_prices_pick_cheapest_plain_product():
    b = shelf.basis_prices(SAMPLE)
    # "Hk. oksekød, 35% grønt" er ikke rent oksekød
    assert b["hakket_okse"]["product"] == "Hk. oksekød 15-18%"
    assert b["maelk"]["price"] == 9.95
    assert b["stegeflaesk"]["product"] == "Stegeflæsk i skiver"
    # 1 stk. agurk omregnes med madplanens vægt pr. stk.; den økologiske tæller ikke
    assert b["agurk"]["price"] == pytest.approx(10 * 1000 / NORMAL_PRICES["agurk"][1])
    assert b["peberfrugt"]["product"] == "Rød peber"


@pytest.mark.parametrize("key, not_product", [
    ("hel_kylling", "Kattemad kylling"), ("bacon", "Baconpostej"), ("champignon", "Sky m/champignon"),
    ("hvidloeg", "Naanbrød, hvidløg"), ("pasta", "Kuglepenne"), ("squash", "Squash orange"),
])
def test_basis_prices_skip_other_products(key, not_product):
    assert shelf.basis_prices(SAMPLE).get(key, {}).get("product") != not_product


def test_citron_yoghurt_is_not_citron():
    # Cheasy citronyoghurt hedder bare "CITRON" men ligger i Mejeri
    assert "citron" not in shelf.basis_prices(SAMPLE)


def test_real_price_replaces_estimate_and_market():
    b = shelf.basis_prices(SAMPLE)
    assert basis_price("maelk", {"maelk": 20}, b) == 9.95
    assert basis_price("maelk", {"maelk": 20}) > 9.95
    ing = {i["key"]: i for i in plan_payload(None, b)["ingredients"]}
    assert ing["maelk"]["price"][0] == 9.95
    assert ing["maelk"]["src"]["store"] == "REMA 1000"
    assert "src" not in ing["linser"]


def test_refresh_keeps_old_prices_on_error(tmp_path, monkeypatch):
    path = tmp_path / shelf.FILE_NAME
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    monkeypatch.setattr(shelf, "fetch_shelf_prices", lambda: SAMPLE)
    prices, error = shelf.refresh(path, now)
    assert error is None and len(prices) == len(SAMPLE)

    def fail():
        raise SourceError("nede")
    monkeypatch.setattr(shelf, "fetch_shelf_prices", fail)
    prices, error = shelf.refresh(path, now + timedelta(days=2))
    assert error == "nede" and len(prices) == len(SAMPLE)
    # Friske priser hentes ikke igen
    assert shelf.refresh(path, now + timedelta(hours=1)) == (prices, None)


def test_fetch_pages(monkeypatch):
    pages = {1: [{"name": "A", "prices": [{"price": 1.0}]}], 2: [{"name": "B", "prices": [{"price": 2.0}]}]}

    def get(url, retries=3):
        page = int(url.split("&page=")[1].split("&")[0])
        return {"data": pages.get(page, []), "meta": {"pagination": {"last_page": 2}}}
    monkeypatch.setattr(rema, "_get", get)
    assert [p.name for p in rema.fetch_shelf_prices()] == ["A", "B"]
