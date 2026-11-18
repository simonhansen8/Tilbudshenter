"""Filtrene over tilbuddene (mellem "// <filters>" og "// </filters>" i app.html).

Et tomt valg betyder "alle", og alle filtre, der er slået til, kan ses som
mærker og fjernes, så man aldrig er låst fast i et valg.
"""

import json
import shutil
import subprocess
from importlib import resources

import pytest

OFFERS = [
    {"id": "1", "dealer": "Netto", "heading": "Kaffe", "description": "Formalet", "category": "kaffe_og_te",
     "price": 30, "known_discount": 40, "member": None, "later": False},
    {"id": "2", "dealer": "Lidl", "heading": "Økologisk letmælk", "description": "1 liter", "category": "mejeri",
     "price": 12, "known_discount": None, "member": "Lidl Plus", "later": False},
    {"id": "3", "dealer": "REMA 1000", "heading": "Tuborg øl", "description": "15 x 33 cl", "category": "oel_og_vin",
     "price": 89, "known_discount": 15, "member": None, "later": True},
    {"id": "4", "dealer": "Netto", "heading": "Opvaskemiddel", "description": "500 ml", "category": "husholdning",
     "price": 20, "known_discount": 25, "member": None, "later": False},
]
CATEGORIES = ["kaffe_og_te", "mejeri", "oel_og_vin", "husholdning"]


def run(code: str, saved: dict | None = None, settings: dict | None = None, basics: bool = False, new_user: bool = False):
    """Kører koden med filtrene og søgningen fra app.html og giver det, koden
    skriver med out(...)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    search = html.split("// <search>", 1)[1].split("\n", 1)[1].split("// </search>", 1)[0]
    filters = html.split("// <filters>", 1)[1].split("// </filters>", 1)[0]
    script = f"""
const saved = {"null" if new_user else json.dumps(saved or {})};
const store = {{get: (k, d) => k === "filters" && saved !== null ? saved : d, set: () => {{}}}};
const panel = {{hidden: true}};
const $ = id => panel;
function money(n) {{ return n + " kr"; }}
const state = {{offers: {json.dumps(OFFERS, ensure_ascii=False)}, categories: {json.dumps([{"key": k, "name": k} for k in CATEGORIES])},
  settings: {json.dumps(settings or {})}, basics: {{on: {json.dumps(basics)}}}, f: null}};
function period(o) {{ return o.later ? "later" : "now"; }}
{search}
function searchFor(query) {{
  if (searchFor.idx?.offers !== state.offers) searchFor.idx = searchIndex(state.offers);
  return searchMatcher(query, searchFor.idx);
}}
{filters}
const shown = () => {{ const ex = excludeTest(); return state.offers.filter(o => !failMask(o, state.basics.on, ex)).map(o => o.id); }};
const result = [];
const out = x => result.push(x);
loadFilters();
{code}
console.log(JSON.stringify(result));
"""
    res = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(res.stdout)


def test_everything_is_shown_from_the_start():
    # Ingen kategorier, butikker eller rabatter er valgt på forhånd
    assert run("out(shown()); out(activeFilters().length);") == [["1", "2", "3", "4"], 0]


def test_a_new_user_starts_with_food_and_drink():
    # Første besøg: kun mad og drikke, som et mærke der kan fjernes
    got = run("out(shown()); out(activeFilters().map(a => a.label)); activeFilters()[0].clear(); out(shown());", new_user=True)
    assert got == [["1", "2", "3"], ["Mad og drikke"], ["1", "2", "3", "4"]]


def test_choosing_a_store_shows_only_that_store():
    got = run("""
      toggleIn(state.f.stores, "Netto", ["Netto", "Lidl", "REMA 1000"]); out(shown());
      toggleIn(state.f.stores, "Lidl", ["Netto", "Lidl", "REMA 1000"]); out(shown());
      // Er alle valgt, er filteret slået fra igen
      toggleIn(state.f.stores, "REMA 1000", ["Netto", "Lidl", "REMA 1000"]); out(state.f.stores.size);
    """)
    assert got == [["1", "4"], ["1", "2", "4"], 0]


def test_active_filters_can_be_removed_one_by_one():
    got = run("""
      state.f.stores.add("Netto"); state.f.discount = "30"; state.f.exclude = ["kaffe"];
      out(shown()); out(activeFilters().map(a => a.label));
      activeFilters().find(a => a.label === "Skjuler kaffe").clear(); out(shown());
      resetFilters(); out(shown());
    """)
    assert got == [[], ["Netto", "Mindst 30 % rabat", "Skjuler kaffe"], ["1"], ["1", "2", "3", "4"]]


def test_discount_steps():
    got = run("""
      for (const d of ["all", "known", "20", "30"]) { state.f.discount = d; out(shown()); }
    """)
    # Mindst x % og "kendt rabat" viser ikke tilbud, hvor rabatten ikke kendes
    assert got == [["1", "2", "3", "4"], ["1", "3", "4"], ["1", "4"], ["1"]]


def test_food_only_and_the_other_filters():
    got = run("""
      state.f.cats = new Set(foodCats()); out(shown()); out(activeFilters().map(a => a.label));
      state.f.cats.clear();
      state.f.maxPrice = 25; out(shown()); state.f.maxPrice = null;
      state.f.hideMember = true; out(shown()); state.f.hideMember = false;
      state.f.periods.add("later"); out(shown()); state.f.periods.clear();
      state.f.exclude = ["øko"]; out(shown());
    """)
    assert got == [["1", "2", "3"], ["Mad og drikke"], ["2", "4"], ["1", "3", "4"], ["3"], ["1", "3", "4"]]


def test_basics_ignore_category_and_discount():
    got = run("""
      state.f.cats.add("mejeri"); state.f.discount = "50"; state.f.stores.add("Netto");
      out(shown()); out(activeFilters().map(a => a.label));
    """, basics=True)
    assert got == [["1", "4"], ["Netto"]]


def test_saved_filters_and_old_settings():
    saved = {"v": 3, "stores": ["Netto", "Føtex"], "cats": ["mejeri"], "discount": "known", "panel": True}
    got = run("pruneFilters(); out([...state.f.stores]); out(shown()); out(panel.hidden);", saved=saved)
    # En butik uden tilbud nu tæller ikke med
    assert got == [["Netto"], [], False]
    # Fra før de nye filtre: de gamle kategorivalg bruges ikke, men skjulte ord
    # og højeste pris fra indstillingerne kan ses og fjernes
    old = {"v": 2, "hiddenCats": ["oel_og_vin"], "hiddenStores": ["Lidl"]}
    settings = {"exclude_keywords": ["øl"], "max_price": 50, "only_known_discount": False}
    got = run("out(shown()); out(activeFilters().map(a => a.label));", saved=old, settings=settings)
    assert got == [["1", "2", "4"], ["Højst 50 kr", "Skjuler øl"]]
