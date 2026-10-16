from dataclasses import replace

from tilbudshenter.comparison import compare_across_stores, product_group
from tilbudshenter.models import Offer
from tilbudshenter.report import discount_text
from tilbudshenter.selection import select_offers


def offer(heading, price, dealer, description="", pre_price=None):
    return Offer(id=f"{dealer}-{heading}-{price}", catalog_id="c", dealer=dealer, heading=heading,
                 description=description, price=price, pre_price=pre_price)


def test_product_group():
    assert product_group("Netto hakket oksekød 14-18%") == "hakket_okse"
    assert product_group("REMA 1000 Hakket dansk grisekød 8-12%") == "hakket_gris"
    assert product_group("MADVÆRKET Hakket grise- og kalvekød") == "hakket_gris_kalv"
    assert product_group("Dansk kyllingebrystfilet eller -inderfilet") == "kyllingebryst"
    assert product_group("Danske skrabeæg") == "aeg"
    # Flere forskellige varer, færdigretter, pålæg og øko sammenlignes ikke
    assert product_group("Hakket okse- eller grise/kalvekød") is None
    assert product_group("Hakket dansk grisekød 8-12% eller medister") is None
    assert product_group("Kyllingefilet med gratin") is None
    assert product_group("PÅLÆGSSLAGTEREN Kyllingebryst") is None
    assert product_group("Änglamark økologisk hakket oksekød 8-12%") is None
    assert product_group("DANISH CROWN Hakket oksekød med 35 % grøntsager") is None
    assert product_group("KAREN VOLF Æbleskiver") is None
    assert product_group("Bruno Banani deodorant") is None


def test_compare_across_stores():
    offers = [
        offer("Netto hakket oksekød", 37.5, "Netto", "500 g"),     # 75 kr/kg
        offer("Hakket oksekød", 45, "Lidl", "500 g"),              # 90 kr/kg
        offer("Hakket oksekød", 50, "føtex", "500 g"),             # 100 kr/kg
        offer("Hakket oksekød", 55, "føtex", "500 g"),             # dyrere i samme butik
        offer("Hakket kalkunkød", 20, "Netto", "500 g"),           # kun én butik
    ]
    result = compare_across_stores(offers)
    netto = result[offers[0].id]
    assert netto.reference == 95  # median af Lidl (90) og føtex (100)
    assert netto.other_stores == 2
    # Lidl (90) er dyrere end medianen af Netto (75) og føtex (100)
    assert offers[1].id not in result
    assert offers[2].id not in result and offers[3].id not in result
    assert offers[4].id not in result


def test_unrealistic_difference_ignored():
    offers = [offer("Hakket oksekød", 10, "Netto", "1 kg"), offer("Hakket oksekød", 100, "Lidl", "1 kg")]
    assert compare_across_stores(offers) == {}


def test_per_piece_only_for_some_groups():
    offers = [offer("Skrabeæg", 20, "Netto", "10 stk"), offer("Skrabeæg", 30, "Lidl", "10 stk"),
              offer("Rugbrød", 15, "Netto", "1 stk"), offer("Rugbrød", 25, "Lidl", "1 stk")]
    result = compare_across_stores(offers)
    assert set(result) == {offers[0].id}


def test_select_uses_comparison_when_no_normal_price(cfg, categorizer):
    offers = [
        offer("Netto hakket oksekød", 37.5, "Netto", "500 g"),
        offer("Hakket oksekød", 50, "Lidl", "500 g"),
        offer("Kaffe", 30, "Lidl", "400 g", pre_price=40),
    ]
    result = select_offers(offers, replace(cfg, stores=[]), categorizer)
    netto = next(o for o in result if o.dealer == "Netto")
    assert netto.discount_basis == "butikker"
    assert round(netto.known_discount) == 25
    assert discount_text(netto) == "ca. -25%"
    assert "billigere end hakket oksekød i 1 anden butik" in netto.reasons[0]
    kaffe = next(o for o in result if o.heading == "Kaffe")
    assert kaffe.discount_basis == "foerpris" and discount_text(kaffe) == "-25%"
    # Normalprisen vinder over sammenligningen
    lidl = next(o for o in result if o.heading == "Hakket oksekød")
    assert lidl.known_discount is None


def test_comparison_only_among_selected_stores(cfg, categorizer):
    offers = [offer("Netto hakket oksekød", 37.5, "Netto", "500 g"),
              offer("Hakket oksekød", 50, "Lidl", "500 g")]
    result = select_offers(offers, replace(cfg, stores=["Netto"]), categorizer)
    assert result[0].known_discount is None


def test_foetex_food_does_not_count_as_another_store():
    # føtex food har føtex' priser, så de to må ikke sammenlignes med hinanden
    offers = [offer("Hakket oksekød", 40, "føtex", "500 g"), offer("Hakket oksekød", 40, "føtex food", "500 g"),
              offer("Hakket oksekød", 50, "Netto", "500 g")]
    result = compare_across_stores(offers)
    assert {o.dealer for o in offers if o.id in result} == {"føtex", "føtex food"}
    assert all(c.other_stores == 1 and c.reference == 100 for c in result.values())
