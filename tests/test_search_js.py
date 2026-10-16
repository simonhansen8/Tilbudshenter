"""Søgningen på tilbudssiden (mellem "// <search>" og "// </search>" i app.html).

Et søgeord skal være et ord, en bøjning af det eller en del af et sammensat
ord, ikke bare de samme bogstaver inde i et andet ord.
"""

import json
import shutil
import subprocess
from importlib import resources

import pytest

OFFERS = [
    ("Skrabeæg", "10 stk.", "mejeri"), ("Frilandsæg", "Økologiske", "mejeri"), ("Æg", "Str. M/L", "mejeri"),
    ("Æggebakke", "Til 6 æg", "mejeri"), ("Pålæg", "Hamburgerryg", "koed"), ("Trusseindlæg", "Normal", "personlig_pleje"),
    ("Køkkenvægt", "Digital", "nonfood"), ("Isbæger", "Vanilje", "frost"), ("Ægte honning", "Dansk", "kolonial"),
    ("Skiveost", "45+", "mejeri"), ("Osten", "Lagret", "mejeri"), ("Dybfrost pizza", "Frost", "frost"),
    ("Juleøl", "Fra Thisted", "oel_og_vin"), ("Pølser", "Grill", "koed"), ("Spegepølse", "Pålæg", "koed"),
    ("Grillrist", "Rustfri", "nonfood"), ("Kaffe", "Formalet", "kaffe_og_te"), ("Instantkaffe", "Glas", "kaffe_og_te"),
    ("Hakket oksekød", "8-12 %", "koed"), ("Te", "Grøn te", "kaffe_og_te"), ("Booster", "Bilsæde", "nonfood"),
    ("Pris", "Hvede", "kolonial"), ("Bakke", "Plast", "nonfood"), ("Pålægschokolade", "Mørk", "slik_og_snacks"),
]


def run(offers: list[tuple[str, str, str]], queries: tuple[str, ...]) -> dict[str, list[list]]:
    """Giver for hvert søgeord de fundne tilbud som [overskrift, niveau]."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <search>", 1)[1].split("\n", 1)[1].split("// </search>", 1)[0]
    data = [{"heading": h, "description": d, "dealer": "Netto", "category": c} for h, d, c in offers]
    script = (f"{block}\nconst offers = {json.dumps(data, ensure_ascii=False)};\n"
              "const idx = searchIndex(offers);\n"
              f"console.log(JSON.stringify(Object.fromEntries({json.dumps(queries, ensure_ascii=False)}.map(q => {{\n"
              "  const m = searchMatcher(q, idx);\n"
              "  return [q, offers.map(o => [o.heading, m(o)]).filter(x => x[1] >= 0)];\n"
              "}))));\n")
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def search(*queries: str) -> dict[str, list[str]]:
    got = run(OFFERS, queries)
    return {q: [h for h, _ in hits] for q, hits in got.items()}


def test_short_words_do_not_match_inside_other_words():
    got = search("æg", "ost", "øl", "te", "ris")
    assert got["æg"] == ["Skrabeæg", "Frilandsæg", "Æg", "Æggebakke"]
    assert got["ost"] == ["Skiveost", "Osten"]
    assert got["øl"] == ["Juleøl"]
    assert got["te"] == ["Te"]
    assert got["ris"] == []


def test_inflections_and_compounds():
    got = search("pølse", "pølser", "kaffe", "Hakket oksekød", "hakket kylling", "PÅLÆG")
    assert got["pølse"] == ["Pølser", "Spegepølse"]
    assert got["pølser"] == ["Pølser", "Spegepølse"]
    assert got["kaffe"] == ["Kaffe", "Instantkaffe"]
    assert got["Hakket oksekød"] == ["Hakket oksekød"]
    assert got["hakket kylling"] == []
    assert got["PÅLÆG"] == ["Pålæg", "Spegepølse"]



FRUIT = [
    ("Bananer", "Pr. kg", "frugt"), ("Økologiske bananer", "", "frugt"), ("Rainforestbanan", "Stk.", "frugt"),
    ("Frugtmarked", "Bananer, kiwi eller æbler", "frugt"), ("Arla Protein drik Vanilje, chokolade eller banan", "", "slik"),
    ("REMA 1000 Is med smag af banan", "6 stk.", "slik"), ("Bruno Banani deodorant", "150 ml", "pleje"),
    ("Danonino", "Jordbær eller banan", "mejeri"),
]


def test_flavours_and_other_categories_come_last():
    got = dict(run(FRUIT, ("banan",))["banan"])
    assert got == {"Bananer": 0, "Økologiske bananer": 0, "Rainforestbanan": 0, "Frugtmarked": 1,
                   "Arla Protein drik Vanilje, chokolade eller banan": 2, "REMA 1000 Is med smag af banan": 2,
                   "Danonino": 2}


def test_minus_leaves_out():
    got = search("pølse -spegepølse", "kaffe -instantkaffe")
    assert got == {"pølse -spegepølse": ["Pølser"], "kaffe -instantkaffe": ["Kaffe"]}


def test_basics_use_the_search():
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    assert "match: searchFor(word)" in html


def test_kitchen_tools_are_not_food():
    offers = [("Änglamark økologiske ris", "1000 g", "kolonial"),
              ("Decilitermål, dejskraber, piskeris, minisigte 8 cm", "20-pak sprøjteposer", "nonfood"),
              ("Sobczyk håndmixer eller røremaskine", "Inkl. piskeris og dejkroge", "nonfood"),
              ("Mælkeskummer", "Kold mælkeskum", "nonfood"), ("Letmælk", "Let eller sød", "mejeri")]
    got = run(offers, ("ris", "mælk"))
    assert got["ris"] == [["Änglamark økologiske ris", 0]]
    assert got["mælk"] == [["Letmælk", 0]]


def test_beans_are_not_coffee():
    offers = [("Kidneybønner", "400 g", "kolonial"), ("Hvide bønner i tomatsauce", "", "kolonial"),
              ("Edamame eller grønne bønner", "Dybfrost", "kolonial"), ("Merrild hele bønner", "1 kg", "kaffe_og_te"),
              ("Lavazza kaffebønner", "1 kg", "kaffe_og_te"), ("Peter Larsen Kaffe", "Formalet", "kaffe_og_te")]
    got = run(offers, ("bønner", "kaffe"))
    assert [h for h, _ in got["bønner"]] == ["Kidneybønner", "Hvide bønner i tomatsauce", "Edamame eller grønne bønner"]
    assert [h for h, _ in got["kaffe"]] == ["Lavazza kaffebønner", "Peter Larsen Kaffe"]


def test_beer_without_the_word():
    offers = [("Thisted eller Skanderborg Bryghus", "50 cl. Ex. pant", "andet"), ("Grøn Tuborg eller Carlsberg Pilsner", "", "oel_og_vin"),
              ("Harboe julebryg", "33 cl.", "oel_og_vin"), ("Tuborg øl", "15 x 33 cl.", "oel_og_vin"),
              ("Tuborg Squash", "33 cl.", "drikkevarer"), ("CRIVIT Skiundertrøje", "Transporterer fugt", "nonfood")]
    got = run(offers, ("øl",))
    assert [h for h, _ in got["øl"]] == ["Thisted eller Skanderborg Bryghus", "Grøn Tuborg eller Carlsberg Pilsner",
                                         "Harboe julebryg", "Tuborg øl"]
