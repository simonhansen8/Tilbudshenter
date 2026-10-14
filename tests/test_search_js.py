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
    ("Skrabeæg", "10 stk."), ("Frilandsæg", "Økologiske"), ("Æg", "Str. M/L"), ("Æggebakke", "Til 6 æg"),
    ("Pålæg", "Hamburgerryg"), ("Trusseindlæg", "Normal"), ("Køkkenvægt", "Digital"), ("Isbæger", "Vanilje"),
    ("Ægte honning", "Dansk"), ("Skiveost", "45+"), ("Osten", "Lagret"), ("Dybfrost pizza", "Frost"),
    ("Juleøl", "Fra Thisted"), ("Pølser", "Grill"), ("Spegepølse", "Pålæg"), ("Grillrist", "Rustfri"),
    ("Kaffe", "Formalet"), ("Instantkaffe", "Glas"), ("Hakket oksekød", "8-12 %"), ("Te", "Grøn te"),
    ("Booster", "Bilsæde"), ("Pris", "Hvede"), ("Bakke", "Plast"), ("Pålægschokolade", "Mørk"),
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
    got = run([(h, d, "x") for h, d in OFFERS], queries)
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
    assert got["PÅLÆG"] == ["Pålæg", "Spegepølse", "Pålægschokolade"]



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
