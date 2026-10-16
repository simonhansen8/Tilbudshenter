"""Browseren læser egne opskrifter med en kopi af reglerne i mealplan.py.

Testen kører kopien (mellem "// <matcher>" og "// </matcher>" i app.html)
i Node og tjekker, at den giver det samme som Python.
"""

import json
import shutil
import subprocess
from importlib import resources

import pytest

from tilbudshenter.mealplan import _recipe_payload, line_keys, parse_line, plan_payload, recipe_from_lines

LINES = [
    "500 g hakket oksekød 8-12 %", "1 kg kartofler", "1 1/2 dl mælk", "½ l fløde", "2-3 gulerødder, i tern",
    "1 dåse hakkede tomater (400 g)", "2 fed hvidløg", "ca. 1,5 dl creme fraiche", "salt og peber", "1 løg",
    "4 kyllingebryst", "400 g pasta, fx penne", "1 pakke bacon", "3 stk. æg", "1 spsk olivenolie", "1 rødløg",
    "250 g champignon eller svampe", "1 l hønsebouillon", "100 g revet ost", "2 porrer", "1 hel kylling",
    "600 g laks", "200 g frosne ærter", "1 squash", "Tuborg Squash", "1 bakke cherrytomater", "1½ dl ris",
    "2 tortillas", "1 knivspids muskat", "500 g hakket kød", "8 æg", "1 pose spinat", "1 broccoli",
    "50 g revet parmesan", "2 romainesalat", "1 bakke cherrytomater", "200 g chorizo, i tern", "1 lime, saften herfra",
    "1 bundt forårsløg", "2 dl græsk yoghurt", "1 tsk fiskesauce", "5 skiver bacon",
    "1 tsk revet ingefær", "1 frisk mozzarella", "2 kugler mozzarella", "100 g fintrevet ost", "50 g revet comté",
    "salt til ris", "2 spsk smør til stegning", "4 laksebøffer", "2 dl sojayoghurt", "Cheddar twist",
]
RECIPES = [
    (["500 g hakket oksekød", "1 løg", "2 fed hvidløg", "1 dåse hakkede tomater", "400 g spaghetti", "salt"], 4),
    (["250 g hakket oksekød", "1 løg", "1 dåse kidneybønner", "1 spsk olie", "4 tortillas"], 2),
    (["1 kg kartofler", "3 porrer", "1 l hønsebouillon", "2 dl fløde"], 6),
    (["4 kyllingebryst", "1 broccoli", "300 g ris", "1 dåse kokosmælk", "2 spsk karry"], 4),
    (["400 g pasta", "150 g bacon", "4 æg", "100 g revet ost"], 4),
    (["500 g hakket oksekød", "1 æg", "2 spsk mælk", "1 løg"], 4),
]


def run_js(code: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <matcher>", 1)[1].split("\n", 1)[1].split("// </matcher>", 1)[0]
    script = (f"let planData = {json.dumps(plan_payload(), ensure_ascii=False)};\n"
              "let ING = Object.fromEntries(planData.ingredients.map(i => [i.key, i]));\n"
              f"{block}\nconsole.log(JSON.stringify({code}));\n")
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_lines_are_read_like_python():
    js = run_js(f"{json.dumps(LINES, ensure_ascii=False)}.map(l => {{ const p = parseLine(l); return [...p, lineKeys(p[2])]; }})")
    for line, got in zip(LINES, js):
        amount, unit, name = parse_line(line)
        assert got == [pytest.approx(amount), unit, name, line_keys(name)], line


def test_recipes_are_read_like_python():
    code = json.dumps([{"id": "x", "name": "Ret", "lines": lines, "persons": persons} for lines, persons in RECIPES],
                      ensure_ascii=False)
    js = run_js(f"{code}.map(d => recipeFromLines(d).recipe)")
    for (lines, persons), got in zip(RECIPES, js):
        recipe, why = recipe_from_lines("x", "Ret", lines, persons)
        assert recipe, why
        want = _recipe_payload(recipe)
        simple = lambda items: [(pytest.approx(i["amount"]), i["unit"], i["name"], i["keys"], i["main"], i["side"])
                                for i in items]
        assert simple(got["items"]) == simple(want["items"]), lines
        assert (got["kind"], got["veg_g"], got["pantry"], got["flags"]) == (
            want["kind"], want["veg_g"], want["pantry"], want.get("flags", [])), lines


FITS = [
    ("fintrevet lagret cheddarost", "Revet mexi-topping", "revet_ost"),
    ("fintrevet lagret cheddarost", "Planet Dairy Revet tex mex eller cheddar", "revet_ost"),
    ("50 g lagret cheddar", "MILBONA Revet pizzatopping", "revet_ost"),
    ("100 g revet ost", "MILBONA Revet pizzatopping", "revet_ost"),
    ("150 g bacon", "Gestus Røget Bacon", "bacon"),
    ("800 g koteletter", "Coop marineret lammeculotte, bbq koteletter eller Rose kylling hele lår", "koteletter"),
    ("4 kyllingelår", "Coop marineret lammeculotte, bbq koteletter eller Rose kylling hele lår", "kyllingelaar"),
    ("2 dl græsk yoghurt", "MADVÆRKET Skyr naturel eller vanilje", "yoghurt"),
    ("300 g jasminris", "Basmati ris", "ris"),
    ("1 citrusfrugt", "Citroner", "citron"),
    ("2 tomater", "Skinkeculotte med tomat & ramsløg", "tomater"),
    ("600 g torsk", "GESTUS PANEREDE OG OVNKLARE FISKEFILETER", "hvid_fisk"),
    ("300 g brune ris", "Jasminris", "ris"),
    ("300 g brune ris", "Ris", "ris"),
    ("500 g hakket oksekød", "Veggie hakket", "hakket_okse"),
    ("2 skiver veggie bacon", "REMA 1000 Bacon i skiver", "bacon"),
]


def test_offer_fits_like_python():
    from tilbudshenter.mealplan import offer_fits

    js = run_js(f"{json.dumps(FITS, ensure_ascii=False)}.map(([l, h, k]) => offerFits(l, h, k))")
    assert js == [offer_fits(*f) for f in FITS]
    assert js == [False, True, False, True, True, False, True, False, False, True, False, False, False, True, False, False]


def test_parts_after_med_are_ignored_like_python():
    heads = ["Grillpølser med tomat & ramsløg", "Kyllingebryst med hud", "Pepsi Max Lime", "Rucola", "Coca-Cola Zero"]
    js = run_js(f"{json.dumps(heads, ensure_ascii=False)}.map(h => lineKeys(h))")
    assert js == [line_keys(h) for h in heads]
    assert "tomater" not in js[0] and js[1:] == [["kyllingebryst"], [], ["rucola"], []]


def test_wrong_kinds_are_not_matched():
    expect = {"1 tsk revet ingefær": [], "1 frisk mozzarella": ["frisk_mozzarella"],
              "100 g fintrevet ost": ["revet_ost"], "50 g revet comté": ["revet_ost"], "salt til ris": [],
              "2 spsk smør til stegning": ["smoer"], "4 laksebøffer": [], "2 dl sojayoghurt": [],
              "Cheddar twist": []}
    for line, keys in expect.items():
        assert line_keys(parse_line(line)[2]) == keys, line
