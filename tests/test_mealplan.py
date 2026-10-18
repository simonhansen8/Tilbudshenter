import json

from tilbudshenter.cli import main
from tilbudshenter.mealplan import (
    BASIS_PACK_G, DEPARTMENTS, INGREDIENTS, MIN_VEG_PER_PERSON, NORMAL_PRICES, RECIPES, VEGETABLES, imported_recipes,
    basis_pack_g, ingredient_keys, ingredient_names, line_keys, load_imported, offer_fits, recipe_from_lines, recipe_items,
    recipes_payload, vegetables_per_person,
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


def test_specific_goods_replace_general_ones():
    assert ingredient_keys("Zanetti Grana Padano") == ["parmesan"]
    assert ingredient_keys("Revet parmesan eller mozzarella") == ["parmesan", "revet_ost"]
    assert ingredient_keys("Rucola") == ["rucola"]
    assert ingredient_keys("Romainesalat eller icebergsalat") == ["romaine", "salat"]
    assert ingredient_keys("Chorizo i skiver") == []
    assert {"chorizo", "avocado", "linser", "lime", "mango"} <= set(INGREDIENTS)


def test_ingredient_names_for_two_goods():
    assert ingredient_names("Xtra! pasta eller Coop hakkede tomater") == {
        "pasta": "Xtra! pasta", "hakkede_tomater": "Coop hakkede tomater"}
    assert ingredient_names("Coop hakket oksekød 14-18%") == {}


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


def test_basis_packs():
    assert set(BASIS_PACK_G) <= set(INGREDIENTS)
    assert basis_pack_g("loeg") == 1000 and basis_pack_g("hakkede_tomater") == 400
    assert all(basis_pack_g(k) >= NORMAL_PRICES[k][1] for k in INGREDIENTS)


def test_recipes_payload_is_json():
    data = json.loads(json.dumps(recipes_payload()))
    bolognese = next(r for r in data if r["id"] == "bolognese")
    assert bolognese["items"][0] == {
        "amount": 500, "unit": "g", "name": "hakket kød (okse eller grise- og kalv)", "keys": ["hakket_okse", "hakket_gris_kalv"],
        "main": True, "side": False, "prices": {"hakket_okse": [110, 500], "hakket_gris_kalv": [80, 500]},
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


def test_slices_are_grams():
    from tilbudshenter.mealplan import parse_line

    # "5 skiver bacon" er omkring 100 g, ikke 5 pakker
    assert parse_line("5 skiver bacon") == (100, "g", "bacon")


def test_imported_recipes_build():
    # Samlingen fra madsiderne skrives af GitHub; alle opskrifter i den skal kunne bruges
    assert len(imported_recipes()) == len(load_imported())
    for r in imported_recipes():
        assert r.source.startswith("http") and any(i.main for i in r.items)


def test_basis_price_follows_the_offers_when_they_are_dearer():
    from tilbudshenter.mealplan import basis_price, market_prices

    offers = [("Hakket oksekød 8-12%", "kg", p) for p in (120, 125, 130, 135, 140, 400)]
    offers += [("Bacon i skiver", "kg", 90)] * 6  # billigere end basisprisen
    offers += [("Danske porrer", "stk", 10)] * 3  # for få tilbud
    market = market_prices(offers)
    assert market == {"hakket_okse": 132.5, "bacon": 90}
    assert basis_price("hakket_okse", market) == 132
    assert basis_price("bacon", market) == 110
    assert basis_price("porrer", market) == 30
    # Højst halvanden gang basisprisen
    assert basis_price("hakket_okse", {"hakket_okse": 400}) == 165


def test_recipe_lines_in_singular_and_spice_blends():
    from tilbudshenter.mealplan import line_keys, parse_line, recipe_from_lines

    keys = lambda line: line_keys(parse_line(line)[2])  # noqa: E731
    assert keys("1 gulerod") == ["guleroedder"]
    assert keys("300 g kartoffel") == ["kartofler"]
    assert keys("450 g sød kartoffel") == []
    assert keys("2 stk Tomat") == ["tomater"]
    assert keys("1 stk Hvidløgsfed") == ["hvidloeg"]
    assert keys("250 g Hakket svine-/kalvekød") == ["hakket_gris_kalv"]
    # Bouillon er ikke kød, og 4 g af en krydderiblanding er et krydderi
    recipe, why = recipe_from_lines("", "Kylling i karry", [
        "300 g kyllingebryst", "1 stk løg", "1 stk hønsebouillonterning", "4 g Jorden Rundt", "4 g Panamad",
        "2 stk gulerod", "400 ml kokosmælk"], 2)
    assert why == "" and {"Jorden Rundt", "hønsebouillonterning"} <= set(recipe.pantry)


def test_more_meat_and_fish_in_offers():
    # Tilbud fra rigtige aviser (oktober 2026), som opskrifterne nu kan bruge
    cases = {
        "Berberieandebryst": ["and"], "Kalkunstrimler af brystfilet": ["kalkun"], "LAMMEKOTELETTER": ["lam"],
        "REMA 1000 Dansk kalveculotte": ["boef", "kalvekoed"], "PremiuM okseculotte eller tyndsteg": ["boef", "oksesteg"],
        "BUTCHER’S Nakkefilet": ["svinekam"], "Næmt skinkestrimler": ["skinkekoed"], "DELUXE Parmaskinke": ["lufttoerret_skinke"],
        "Salling Princip varmrøget laks": ["roeget_laks"], "Netto nakkekoteletter": ["koteletter"],
        # Ikke kalvekød, selv om ordet står der
        "Røget bacon, hakket okse eller grise/kalvekød": ["bacon", "hakket_okse"],
        "Coop gulerødder fra Lammefjordspakkeriet": ["guleroedder"],
    }
    for heading, keys in cases.items():
        assert ingredient_keys(heading) == keys, heading
    assert ingredient_keys("Oscar confiteret andebryst") == []
    assert ingredient_keys("PÅLÆGSSLAGTEREN Kalkunbryst") == []


def test_recipe_lines_with_more_meat():
    assert line_keys("hakket lammekød") == ["lam"] and line_keys("svinekamfilet") == ["svinekam"]
    assert line_keys("oksemørbrad") == ["oksemoerbrad"] and line_keys("wokstrimler af okseklump") == ["okse_tern"]
    assert line_keys("hakket kalv og flæsk, 8-12%") == ["hakket_gris_kalv"] and line_keys("bøftomat") == ["tomater"]
    # Hakket lammekød kan ikke laves af lammekoteletter, andebryst ikke af andelår
    assert not offer_fits("hakket lammekød", "LAMMEKOTELETTER", "lam")
    assert offer_fits("andebryster", "Andebryst eller andelår", "and")
    assert not offer_fits("andebryster", "Salling Princip berberi andelår", "and")
    assert not offer_fits("koldrøget laks", "Salling Princip varmrøget laks", "roeget_laks")
    # "Risvin" og "kødsnor" er ikke kød
    recipe, why = recipe_from_lines("x", "Wok", ["400 g kyllingebryst", "2 spsk risvin", "1 stk kødsnor", "200 g ris"])
    assert recipe and not why
    lam, _ = recipe_from_lines("l", "Lam", ["800 g lammekølle", "1 kg kartofler", "2 løg"])
    assert lam.kind == "okse"


def test_steak_in_recipe_is_beef():
    from tilbudshenter.mealplan import recipe_from_lines

    # "Rumpsteak" uden mængde var en ukendt vare, og retten blev en "vegetarret" på tilbud
    name = "Lynstegt rumpsteak i estragonsauce"
    lines = ["300 g Rumpsteak", "500 g små kartofler", "1,5 dl madlavningsfløde", "1 gulerod", "1 stk Estragon"]
    recipe, _ = recipe_from_lines("x", name, lines)
    assert recipe.kind == "okse"
    assert [i.keys for i in recipe.items if i.main] == [["boef"]]
    assert line_keys("oksesteak") == ["boef"]
    assert line_keys("steaks") == ["boef"] and line_keys("tunsteak") == [] and line_keys("steaksauce") == []
    assert line_keys("steakhouse fritter") == [] and line_keys("tunbøffer") == []
    # Uden mængde kan kødet ikke prissættes, og så bruges retten ikke
    assert recipe_from_lines("x", name, ["Rumpsteak", *lines[1:]])[0] is None


def test_meat_in_name_needs_meat_in_ingredients():
    from tilbudshenter.mealplan import recipe_from_lines

    veg = ["400 g pasta", "1 broccoli", "100 g revet ost"]
    assert recipe_from_lines("x", "Pasta med frikadeller", veg + ["8 færdige frikadeller"])[0] is None
    assert recipe_from_lines("x", "Steak med ovnbagte gulerødder", ["1 kg gulerødder", "1 løg", "2 dl fløde"])[0] is None
    # Ikke kød: grøntsagsbøffer, "uden kød" og engelsk "and"
    for name in ["Mac and cheese", "Pasta med aubergine - nem pastaret uden kød", "Grøntsagsbøf med brun sovs"]:
        recipe, why = recipe_from_lines("x", name, veg)
        assert recipe and recipe.kind == "vegetar", (name, why)


def test_broken_recipe_file_stops_the_build(tmp_path):
    import pytest

    # En halvt flettet fil gav en side uden de hentede opskrifter og deres links
    path = tmp_path / "opskrifter.json"
    path.write_text('{"recipes": [\n<<<<<<< HEAD\n]}', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_imported(path)
    assert load_imported(tmp_path / "findes-ikke.json") == []
