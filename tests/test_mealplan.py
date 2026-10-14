import json

from tilbudshenter.cli import main
from tilbudshenter.mealplan import INGREDIENTS, RECIPES, ingredient_keys, recipes_payload


def test_ingredient_keys():
    assert ingredient_keys("Coop hakket oksekød 14-18%") == ["hakket_okse"]
    assert ingredient_keys("Hakket svinekød 8-12%") == ["hakket_gris"]
    assert ingredient_keys("Dansk kyllingebrystfilet, -inderfilet eller hakket kyllingekød 3-7%") == [
        "kyllingebryst", "hakket_kylling"]
    assert ingredient_keys("Coop koteletter eller Rose hele kyllingelår") == ["koteletter", "kyllingelaar"]
    assert ingredient_keys("Coop creme fraiche eller fraiche") == ["creme_fraiche"]
    assert ingredient_keys("MILBONA Revet mozzarella") == ["revet_ost"]
    assert ingredient_keys("Danske porrer") == ["porrer"]


def test_ingredient_keys_skip_non_raw_goods():
    for heading in [
        "LUPILU Batteridrevet legeværktøj",  # "revet"
        "Fløde-kartofler",
        "Coca-Cola, Fanta eller Tuborg Squash",
        "Anthon Berg Tærter",  # "ærter"
        "Zelected Syltede rødløg, agurker, aioli eller sauce",
        "Irma gastrik, æble- eller pærecidereddike",
        "RAHBEK Indbagt laks med spinat eller rejer med asparges",
        "De Cecco pastasauce",
        "FRESHONA Broccoli- eller blomkålsris",
        "GRILLMESTER Kalkunhakkebøffer",
    ]:
        assert "blomkaal" not in ingredient_keys(heading)
        assert set(ingredient_keys(heading)) <= {"broccoli"}, heading


def test_recipes_are_consistent():
    ids = [r.id for r in RECIPES]
    assert len(ids) == len(set(ids)) >= 30
    for r in RECIPES:
        assert r.kind in {"okse", "gris", "kylling", "fisk", "vegetar"}
        assert any(i.main for i in r.items), r.id
        assert r.method and r.minutes > 0
        for i in r.items:
            assert i.keys and all(k in INGREDIENTS for k in i.keys), (r.id, i.name)
            assert i.amount > 0 and i.unit


def test_recipes_payload_is_json():
    data = json.loads(json.dumps(recipes_payload()))
    bolognese = next(r for r in data if r["id"] == "bolognese")
    assert bolognese["items"][0] == {
        "amount": 500, "unit": "g", "name": "hakket oksekød", "keys": ["hakket_okse", "hakket_gris_kalv"],
        "main": True,
    }


def test_site_has_recipes_and_ingredients(tmp_path):
    out = tmp_path / "side"
    assert main(["side", "--demo", "--ud", str(out)]) == 0
    data = json.loads((out / "data.json").read_text("utf-8"))
    assert len(data["recipes"]) == len(RECIPES)
    tagged = {o["heading"]: o["ingredients"] for o in data["offers"] if "ingredients" in o}
    assert tagged["Hakket oksekød 8-12%"] == ["hakket_okse"]
    assert "ingredients" not in next(o for o in data["offers"] if o["heading"] == "Toiletpapir")
