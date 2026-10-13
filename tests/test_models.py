import pytest

from tilbudshenter.models import Offer, parse_quantity, parse_reference_price, parse_stated_unit_price


@pytest.mark.parametrize(
    "text, expected",
    [
        ("500 g", (0.5, "kg")),
        ("1,5 kg", (1.5, "kg")),
        ("6 x 33 cl", (1.98, "l")),
        ("Kyllingebryst 900-1000 g", (0.9, "kg")),
        ("400 gram", (0.4, "kg")),
        ("10 stk", (10, "stk")),
        ("Max 3 stk. pr. kunde. 1 l", (1.0, "l")),
        ("Hakket oksekød 8-12%", None),
        ("", None),
    ],
)
def test_parse_quantity(text, expected):
    result = parse_quantity(text)
    if expected is None:
        assert result is None
    else:
        assert result[0] == pytest.approx(expected[0])
        assert result[1] == expected[1]


def test_offer_derived_values():
    offer = Offer(id="1", catalog_id="c", dealer="Netto", heading="Kaffe", description="400 g",
                  price=30, pre_price=50)
    assert offer.amount == pytest.approx(0.4)
    assert offer.unit_price == pytest.approx(75)
    assert offer.discount_pct == pytest.approx(40)
    assert offer.savings == pytest.approx(20)


def test_offer_without_pre_price_or_quantity():
    offer = Offer(id="1", catalog_id="c", dealer="Netto", heading="Franskbrød", price=12)
    assert offer.discount_pct is None
    assert offer.unit_price is None


def test_pre_price_lower_than_price_is_not_a_discount():
    offer = Offer(id="1", catalog_id="c", dealer="Netto", heading="X", price=20, pre_price=15)
    assert offer.discount_pct is None


@pytest.mark.parametrize(
    "text, price, expected",
    [
        ("175 cm høj / Normalpris 799,- / Spar 159,80", 639.2, 799.0),
        ("Normalpris 1.999,-", 999, 1999.0),
        ("Spar 43,80", 175.2, 219.0),
        ("Spar 10,-", 40, 50.0),
        ("400 g. Pr. kg 49,88 Spar 25 % Fast lav pris", 19.95, 26.6),
        ("Før 30,00", 20, 30.0),
        ("Spar 13-35 %", 12.95, None),  # interval
        ("Normalpris op til 78,- Spar op til 18,-", 60, None),  # "op til"
        ("140 x 220 cm 152,- normalpris 190,- Normalpris 170,-", 136, None),  # flere priser
        ("Normalpris 50,-", 60, None),  # lavere end prisen
        ("Dansk. 500 g", 30, None),
    ],
)
def test_parse_reference_price(text, price, expected):
    assert parse_reference_price(text, price) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("500 g. Pr. kg 70,00 Maks. 3 pk.", (70.0, "kg")),
        ("Pr. kg maks. 78,00", (78.0, "kg")),
        ("24 x 33 cl. Pr. liter 8,71", (8.71, "l")),
        ("Pr. l 42,42", (42.42, "l")),
        ("Pr. kg max. v/merkøb 225.-", None),
        ("Pr. stk.", None),
    ],
)
def test_parse_stated_unit_price(text, expected):
    assert parse_stated_unit_price(text) == expected


def test_enrich_from_text():
    offer = Offer(id="1", catalog_id="c", dealer="Lidl", heading="Bacon",
                  description="2 x 250 g. Pr. kg 70,00. Spar 25 %", price=35)
    offer.enrich_from_text()
    assert offer.unit_price == pytest.approx(70)
    assert offer.unit == "kg"
    assert offer.pre_price == pytest.approx(46.67)
