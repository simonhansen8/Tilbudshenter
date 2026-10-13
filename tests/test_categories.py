import pytest

from tilbudshenter.categories import UNCATEGORIZED, Categorizer, merge_categories


@pytest.mark.parametrize(
    "heading, expected",
    [
        ("Hakket oksekød 8-12%", "koed"),
        ("Kyllingebryst", "koed"),
        ("Gammeldags oksesteg", "koed"),
        ("Marabou mælkechokolade", "slik_og_snacks"),
        ("Arla letmælk", "mejeri"),
        ("Vandmelon", "frugt_og_groent"),
        ("Vindruer", "frugt_og_groent"),
        ("Rødvin fra Italien", "oel_og_vin"),
        ("Svinekød i strimler", "koed"),
        ("Tunfisk i vand", "fisk"),
        ("Hvidløgsflutes", "broed_og_bager"),
        ("Coca-Cola 24 x 33 cl", "drikkevarer"),
        ("Pampers bleer", "baby"),
        ("Danske skrabeæg", "mejeri"),
        ("JACOBSEN Specialøl", "oel_og_vin"),
        ("MADVÆRKET Danbo med kommen", "mejeri"),
        ("Hatting kanelsnegle eller tebirkes", "broed_og_bager"),
        ("SILVERCREST Elkedel", "nonfood"),
        ("Samsung TQ43Q8F", "nonfood"),
        ("RAHBEK Indbagt laks med spinat", "fisk"),
        ("TASTINO Smørcroissanter", "broed_og_bager"),
        ("Mette skammel", "nonfood"),
        ("Noget helt ukendt", UNCATEGORIZED),
    ],
)
def test_default_categories(heading, expected):
    assert Categorizer().categorize(heading) == expected


def test_heading_beats_description():
    assert Categorizer().categorize("Kyllingebryst", "Lækker med salat og ost") == "koed"


def test_description_used_when_heading_is_unknown():
    assert Categorizer().categorize("Tilbud", "Dansk hakket oksekød") == "koed"


def test_custom_category_and_extra_keywords():
    merged = merge_categories({
        "morgenmad": {"navn": "Morgenmad", "noegleord": ["havregryn", "skyr"]},
        "koed": {"noegleord": ["tatar"]},
    })
    c = Categorizer(merged)
    assert c.categorize("Havregryn") == "morgenmad"
    assert c.categorize("Tatar") == "koed"
    assert c.display_name("morgenmad") == "Morgenmad"


def test_price_text_is_not_rice():
    # "Prisen" må ikke matche nøgleordet "ris"
    assert Categorizer().categorize("Apparat", "Prisen gælder kun i dag") == UNCATEGORIZED
