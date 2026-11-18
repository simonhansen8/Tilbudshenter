"""Madplanens dage og slags ret (mellem "// <plan-days>" og "// </plan-days>"
i app.html), kørt i Node."""

import json
import shutil
import subprocess
from functools import cache
from importlib import resources

import pytest

from tilbudshenter.mealplan import plan_payload


@cache
def payload() -> str:
    # Uden opskrifterne; de skal ikke bruges her
    return json.dumps({k: v for k, v in plan_payload().items() if k != "recipes"}, ensure_ascii=False)


def run_js(code: str, plan: dict | None = None) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")

    def block(name: str) -> str:
        return html.split(f"// <{name}>", 1)[1].split("\n", 1)[1].split(f"// </{name}>", 1)[0]

    plan = {"ids": [], "count": 5, "start": "2026-11-18", "off": {}, "double": [], **(plan or {})}
    script = (
        "process.env.TZ = 'Europe/Copenhagen';\n"
        f"let planData = {payload()};\n"
        "let ING = Object.fromEntries(planData.ingredients.map(i => [i.key, i]));\n"
        "const WEEKDAYS = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];\n"
        f"const plan = {json.dumps(plan)}; plan.double = new Set(plan.double);\n"
        f"{block('matcher')}\n{block('days')}\n{block('plan-days')}\n"
        # Dagene regnes fra "i dag" = onsdag 18. november 2026
        "today = () => new Date(2026, 10, 18, 12);\n"
        f"console.log(JSON.stringify({code}));\n"
    )
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_dish_types_keep_the_week_varied():
    names = ["Gammeldags frikadeller", "Blomkålsfrikadeller", "Frikadeller alá mormor", "Spinattærte uden bund",
             "Quiche med græskar, spinat og feta", "Kylling med kartoffelsalat", "Pasta med laks", "Cremet tagliatelle med laks",
             "Kartoffel- og porresuppe"]
    got = run_js(f"{json.dumps(names, ensure_ascii=False)}.map(name => dishType({{name}}))")
    assert got[0] == got[1] == got[2] >= 0
    assert got[3] == got[4] >= 0 and got[3] != got[0]
    assert got[5] == -1
    assert got[6] == got[7] >= 0
    assert got[8] >= 0 and len({got[0], got[3], got[6], got[8]}) == 4


def test_free_days_keep_the_other_dishes_in_place():
    # Onsdag til søndag; fredag er uden aftensmad, og onsdagens ret er en dobbelt portion
    plan = {"ids": ["a", "b", "c"], "double": ["a"], "off": {"2026-11-20": "fri"}}
    got = run_js("[freeDays().map(isoDay), dishSlots(), dishSlots(['a', 'b', 'c'], new Set())]", plan)
    assert got[0] == ["2026-11-18", "2026-11-19", "2026-11-21", "2026-11-22"]
    # a dækker onsdag og torsdag, fredag er fri, b lørdag og c søndag
    assert got[1] == 3
    assert got[2] == 4


def test_long_dishes_and_roasts():
    recipes = [
        {"name": "Flæskesteg", "minutes": 0, "items": [{"main": True, "keys": ["flaeskesteg"]}]},
        {"name": "Krebinetter", "minutes": 0, "items": [{"main": True, "keys": ["hakket_gris"]}]},
        {"name": "Gullasch", "minutes": 120, "items": [{"main": True, "keys": ["okse_tern"]}]},
    ]
    got = run_js(f"{json.dumps(recipes, ensure_ascii=False)}.map(r => [dishMinutes(r), isSlow({{recipe: r}})])")
    assert got == [[120, True], [0, False], [120, True]]
    assert run_js("freeDays().filter(isWeekend).map(isoDay)") == ["2026-11-20", "2026-11-21", "2026-11-22"]
