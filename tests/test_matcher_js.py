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
]
RECIPES = [
    (["500 g hakket oksekød", "1 løg", "2 fed hvidløg", "1 dåse hakkede tomater", "400 g spaghetti", "salt"], 4),
    (["250 g hakket oksekød", "1 løg", "1 dåse kidneybønner", "1 spsk olie", "4 tortillas"], 2),
    (["1 kg kartofler", "3 porrer", "1 l hønsebouillon", "2 dl fløde"], 6),
    (["4 kyllingebryst", "1 broccoli", "300 g ris", "1 dåse kokosmælk", "2 spsk karry"], 4),
    (["400 g pasta", "150 g bacon", "4 æg", "100 g revet ost"], 4),
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
