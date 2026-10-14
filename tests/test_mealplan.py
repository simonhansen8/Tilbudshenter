import json

from tilbudshenter.cli import main
from tilbudshenter.mealplan import (
    DEPARTMENTS, INGREDIENTS, MIN_VEG_PER_PERSON, NORMAL_PRICES, RECIPES, VEGETABLES, imported_recipes,
    ingredient_keys, load_imported, recipe_items, recipes_payload, vegetables_per_person,
)


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
        "Butternut squash",
        "FRESHONA Broccoli- eller blomkålsris",
        "GRILLMESTER Kalkunhakkebøffer",
        "San Marco Pizza med hvidløg & ost",
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
            # Stk, dåser osv. kan kun prissættes med en vægt pr. stk
            price_kg, piece_g = NORMAL_PRICES[i.keys[0]]
            assert price_kg > 0 and (i.unit in ("g", "dl") or piece_g > 0), (r.id, i.name)


def test_every_ingredient_has_a_normal_price():
    assert set(NORMAL_PRICES) == set(INGREDIENTS)


def test_recipes_payload_is_json():
    data = json.loads(json.dumps(recipes_payload()))
    bolognese = next(r for r in data if r["id"] == "bolognese")
    assert bolognese["items"][0] == {
        "amount": 500, "unit": "g", "name": "hakket kød (okse eller grise- og kalv)", "keys": ["hakket_okse", "hakket_gris_kalv"],
        "main": True, "side": False, "prices": {"hakket_okse": [100, 500], "hakket_gris_kalv": [75, 500]},
    }
    assert bolognese["veg_g"] == 278


def test_dishes_with_few_vegetables_get_a_side():
    carbonara = next(r for r in RECIPES if r.id == "carbonara")
    assert vegetables_per_person(carbonara.items) == 0
    side = recipe_items(carbonara)[-1]
    assert side.keys and all(k in VEGETABLES for k in side.keys)
    assert vegetables_per_person(recipe_items(carbonara)) >= MIN_VEG_PER_PERSON
    chili = next(r for r in RECIPES if r.id == "chili")
    assert recipe_items(chili) == chili.items
    data = {r["id"]: r for r in recipes_payload()}
    assert data["carbonara"]["items"][-1]["side"] and data["carbonara"]["veg_g"] == 125


def test_site_has_recipes_and_ingredients(tmp_path):
    out = tmp_path / "side"
    assert main(["side", "--demo", "--ud", str(out)]) == 0
    data = json.loads((out / "data.json").read_text("utf-8"))
    plan = data["plan"]
    assert len(plan["recipes"]) >= len(RECIPES)
    assert {i["key"] for i in plan["ingredients"]} == set(INGREDIENTS)
    assert plan["side"]["side"] and plan["words"]["pantry"]
    tagged = {o["heading"]: o["ingredients"] for o in data["offers"] if "ingredients" in o}
    assert tagged["Hakket oksekød 8-12%"] == ["hakket_okse"]
    assert "ingredients" not in next(o for o in data["offers"] if o["heading"] == "Toiletpapir")


def test_departments_are_categories():
    from tilbudshenter.categories import DEFAULT_CATEGORIES

    assert set(DEPARTMENTS) <= set(INGREDIENTS)
    assert set(DEPARTMENTS.values()) <= set(DEFAULT_CATEGORIES)


def test_imported_recipes_build():
    # Samlingen fra madsiderne skrives af GitHub; alle opskrifter i den skal kunne bruges
    assert len(imported_recipes()) == len(load_imported())
    for r in imported_recipes():
        assert r.source.startswith("http") and any(i.main for i in r.items)
