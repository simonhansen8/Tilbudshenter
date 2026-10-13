import pytest

from tilbudshenter.models import Offer, parse_quantity


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
