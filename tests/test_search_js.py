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


def search(*queries: str) -> dict[str, list[str]]:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <search>", 1)[1].split("\n", 1)[1].split("// </search>", 1)[0]
    offers = [{"heading": h, "description": d} for h, d in OFFERS]
    script = (f"{block}\nconst offers = {json.dumps(offers, ensure_ascii=False)};\n"
              "const vocab = searchVocab(offers);\n"
              f"console.log(JSON.stringify(Object.fromEntries({json.dumps(queries, ensure_ascii=False)}.map(q => {{\n"
              "  const m = searchMatcher(q, vocab);\n"
              "  return [q, offers.filter(o => m(o.heading, o.description) >= 0).map(o => o.heading)];\n"
              "}))));\n")
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


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

