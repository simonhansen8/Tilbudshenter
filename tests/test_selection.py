from dataclasses import replace

from tilbudshenter.models import Offer
from tilbudshenter.selection import select_offers, store_selected


def offer(heading, price, pre_price=None, dealer="Netto", description="", id=None):
    return Offer(id=id or heading, catalog_id="c", dealer=dealer, heading=heading,
                 description=description, price=price, pre_price=pre_price)


def test_store_matching(cfg):
    cfg = replace(cfg, stores=["rema 1000", "Coop 365"])
    assert store_selected("REMA 1000", cfg)
    assert store_selected("Coop 365discount", cfg)
    assert not store_selected("Netto", cfg)
    assert store_selected("Netto", replace(cfg, stores=[]))
    assert not store_selected("Netto", replace(cfg, stores=[], exclude_stores=["netto"]))


def test_sorted_by_discount(cfg, categorizer):
    offers = [offer("Mælk", 8, 10), offer("Kaffe", 30, 60), offer("Smør", 15, 20)]
    result = select_offers(offers, cfg, categorizer)
    assert [o.heading for o in result] == ["Kaffe", "Smør", "Mælk"]


def test_filters(cfg, categorizer):
    offers = [
        offer("Kyllingebryst", 40, 60),
        offer("Rødvin", 40, 80),
        offer("Laks", 200, 300),
        offer("Franskbrød", 12),  # ingen førpris
        offer("Hakket oksekød", 30, 32),
    ]
    cfg = replace(cfg, categories=["koed", "fisk", "broed_og_bager"], max_price=150, min_discount_pct=20)
    assert [o.heading for o in select_offers(offers, cfg, categorizer)] == ["Kyllingebryst"]


def test_keywords_and_favorites(cfg, categorizer):
    offers = [offer("Kaffe", 40, 50), offer("Kakao", 10, 30), offer("Chips", 5, 20)]
    cfg = replace(cfg, favorites=["kaffe"], exclude_keywords=["chips"], min_discount_pct=50)
    result = select_offers(offers, cfg, categorizer)
    # Kaffe har kun 20% rabat, men er favorit og kommer med
    assert [o.heading for o in result] == ["Kakao", "Kaffe"]
    assert "favorit (kaffe)" in result[1].reasons


def test_history_used_when_no_pre_price(cfg, categorizer):
    o = offer("Hakket oksekød", 30, description="500 g")
    typical = {("hakket oksekød", "kg"): 100.0}
    result = select_offers([o], replace(cfg, min_discount_pct=30), categorizer, typical)
    assert result and round(result[0].score) == 40
    assert "under normal enhedspris" in result[0].reasons[0]


def test_per_category_and_limit(cfg, categorizer):
    offers = [offer(f"Kaffe {i}", 10, 20 + i, id=str(i)) for i in range(5)] + [offer("Mælk", 5, 10)]
    result = select_offers(offers, replace(cfg, per_category=2), categorizer)
    assert [o.category for o in result].count("kaffe_og_te") == 2
    assert len(select_offers(offers, cfg, categorizer, limit=3)) == 3


def test_duplicate_offers_removed(cfg, categorizer):
    offers = [offer("Kaffe", 30, 60, id="a"), offer("Kaffe", 30, 60, id="b")]
    assert len(select_offers(offers, cfg, categorizer)) == 1
