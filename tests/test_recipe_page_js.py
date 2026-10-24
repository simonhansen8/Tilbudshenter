"""Opskrifter fra et link på GitHub Pages: browserens udgave af
extract_recipe (mellem "// <recipe-page>" og "// </recipe-page>" i app.html)
skal læse siderne som Python-udgaven."""

import json
import shutil
import subprocess
from importlib import resources

import pytest

from test_opskrifter import PAGE
from tilbudshenter.opskrifter import extract_recipe

MICRODATA = """<html><head><title>Chili con carne - Valdemarsro</title>
<script type="application/ld+json">{"@graph": [{"@type": "Article", "headline": "Chili"}]}</script></head>
<body><div itemscope itemtype="https://schema.org/Recipe"><h1>Chili con carne</h1>
<meta itemprop="recipeYield" content="4 personer"><meta itemprop="totalTime" content="PT45M">
<ul><li itemprop="recipeIngredient">500 g hakket oksek&oslash;d</li>
<li class="ing" itemprop="recipeIngredient"><span>1</span> løg</li></ul>
<div itemprop="recipeInstructions"><p>Brun kødet.</p></div></div></body></html>"""

EMBEDDED = """<html><head><meta property="og:title" content="Lasagne | Arla"></head><body>
<script>window.__DATA__ = {"page": {"type": "recipe", "recipe": {"@type": "Recipe", "id": 7,
  "recipeCategory": "Frokost, Aftensmad", "info": {"x": "{ikke json}"},
  "recipeIngredient": ["300 g hakket oksekød", "1 løg"], "recipeYield": "4"}}};</script></body></html>"""

ESCAPED = '<html><head><title>Suppe</title></head><body><script>var s = "{\\"name\\":\\"Suppe\\",\\"recipeIngredient\\":[\\"2 gulerødder\\"]}";</script></body></html>'

NONE = "<html><head><title>Forside</title></head><body><p>Ingen opskrift her</p></body></html>"


def run_js(pages: list[str]) -> list:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <recipe-page>", 1)[1].split("// </recipe-page>", 1)[0]
    script = f"{block}\nconsole.log(JSON.stringify({json.dumps(pages)}.map(p => extractRecipe(p, 'https://mad.dk/x'))));\n"
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("page", [PAGE, MICRODATA, EMBEDDED, ESCAPED, NONE], ids=["ld-json", "microdata", "embedded", "escaped", "none"])
def test_browser_reads_recipe_pages_like_python(page):
    got = run_js([page])[0]
    want = extract_recipe(page, "https://mad.dk/x")
    if want is None:
        assert got is None
        return
    assert got == {k: want[k] for k in ("url", "name", "persons", "minutes", "ingredients", "method")}


def test_browser_recipe_fields():
    chili, micro = run_js([PAGE, MICRODATA])
    assert chili["name"] == "Chili con carne & ris" and chili["persons"] == 2 and chili["minutes"] == 65
    assert chili["method"] == "Brun kødet. Kog ris."
    assert micro["ingredients"] == ["500 g hakket oksekød", "1 løg"] and micro["minutes"] == 45


DR_TEXT = """Title: Lasagne | DR

URL Source: https://www.dr.dk/mad/opskrift/lasagne

**Tidsforbrug:** 1 time, 10 min. **Mængde:** 4 pers.

## Ingredienser

**Kødsauce**

*   •

2 spsk. olivenolie

*   •

500 g hakket oksekød

*   •

1 dåse flåede tomater

**Bechamelsauce**

*   •

0,5 l mælk

## Fremgangsmåde

Tænd ovnen på 200 grader.
"""

ARLA_TEXT = """Title: Lasagne - Arla

## Ingredienser

 4 personer 

### Kødsauce

| 25 g Smør |  |
| --- |
| 500 g Hakket oksekød |  |
| 1 Hakket løg (ca. 100 g) |  |

### Mornaysauce

| 6 dl Kogende mælk |  |

## Sådan gør du

Smelt smørret.
"""


def run_text_js(texts: list[str]) -> list:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <recipe-page>", 1)[1].split("// </recipe-page>", 1)[0]
    script = f"{block}\nconsole.log(JSON.stringify({json.dumps(texts)}.map(t => extractRecipeText(t, 'https://mad.dk/x'))));\n"
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_recipe_from_page_text():
    # Sider uden schema.org/Recipe (fx DR) læses som tekst fra r.jina.ai
    dr, arla, none = run_text_js([DR_TEXT, ARLA_TEXT, "Title: Forside\n\nIngen opskrift"])
    assert dr["name"] == "Lasagne" and dr["persons"] == 4
    assert dr["ingredients"] == ["2 spsk. olivenolie", "500 g hakket oksekød", "1 dåse flåede tomater", "0,5 l mælk"]
    assert arla["name"] == "Lasagne"
    assert arla["ingredients"] == ["25 g Smør", "500 g Hakket oksekød", "1 Hakket løg (ca. 100 g)", "6 dl Kogende mælk"]
    assert none is None
