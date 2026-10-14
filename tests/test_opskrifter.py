import json

from tilbudshenter.cli import main
from tilbudshenter.mealplan import parse_line, recipe_from_lines
from tilbudshenter.opskrifter import _minutes, extract_recipe, is_dinner, update

PAGE = """<html><head>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "WebSite", "name": "Madsiden"}</script>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "BreadcrumbList"},
  {"@type": ["Recipe"], "name": "Chili con carne &amp; ris", "recipeYield": ["2", "2 personer"],
   "recipeCategory": ["Aftensmad", "Hovedret"],
   "totalTime": "PT1H5M",
   "recipeIngredient": ["250 g hakket oksekød", "1 løg", "1 dåse hakkede tomater", "1 dåse kidneybønner",
                        "1 rød peberfrugt", "150 g ris", "1 tsk spidskommen", "salt og peber"],
   "recipeInstructions": [{"@type": "HowToSection", "itemListElement": [
      {"@type": "HowToStep", "text": "Brun kødet."}, {"@type": "HowToStep", "text": "Kog <b>ris</b>."}]}]}
]}
</script></head><body></body></html>"""


def test_parse_line():
    assert parse_line("500 g hakket oksekød") == (500, "g", "hakket oksekød")
    assert parse_line("1 kg kartofler") == (1000, "g", "kartofler")
    assert parse_line("1 1/2 dl mælk") == (1.5, "dl", "mælk")
    assert parse_line("½ l fløde") == (5, "dl", "fløde")
    assert parse_line("2-3 gulerødder, i tern") == (2.5, "stk", "gulerødder, i tern")
    assert parse_line("1 dåse hakkede tomater (400 g)") == (1, "dåse", "hakkede tomater")
    assert parse_line("2 fed hvidløg") == (2, "fed", "hvidløg")
    assert parse_line("ca. 1,5 dl creme fraiche") == (1.5, "dl", "creme fraiche")
    assert parse_line("salt og peber") == (0, "", "salt og peber")


def test_recipe_from_lines():
    recipe, why = recipe_from_lines("x", "Chili", ["250 g hakket oksekød", "1 løg", "1 dåse kidneybønner",
                                                     "1 spsk olie", "4 tortillas"], persons=2)
    assert not why and recipe.kind == "okse"
    first = recipe.items[0]
    assert (first.amount, first.unit, first.keys, first.main) == (500, "g", ["hakket_okse"], True)
    assert [i.keys[0] for i in recipe.items] == ["hakket_okse", "loeg", "kidneyboenner", "tortilla"]
    assert recipe.pantry == ["olie"]
    # Kød der ikke kan genkendes, kan ikke prissættes og passer ikke til en vegetar
    assert recipe_from_lines("y", "Lam", ["800 g lammekølle", "1 kg kartofler", "2 løg"])[0] is None
    # Bouillon er en basisvare, men retten passer så ikke til en vegetar
    soup, _ = recipe_from_lines("s", "Suppe", ["1 kg kartofler", "3 porrer", "1 l hønsebouillon"])
    assert soup.kind == "vegetar" and soup.flags == ["meat"] and soup.pantry == ["hønsebouillon"]
    veg, _ = recipe_from_lines("z", "Suppe", ["1 kg kartofler", "3 porrer", "2 dl fløde"])
    assert veg.kind == "vegetar" and [i.name for i in veg.items if i.main] == ["kartofler", "porrer"]


def test_minutes():
    assert _minutes("PT1H30M") == 90 and _minutes("PT45M") == 45 and _minutes("P0DT0H20M") == 20
    assert _minutes("") == 0 and _minutes("30 min") == 0


def test_extract_recipe():
    data = extract_recipe(PAGE, "https://mad.dk/chili")
    assert data == {
        "url": "https://mad.dk/chili", "name": "Chili con carne & ris", "category": "Aftensmad, Hovedret",
        "persons": 2, "minutes": 65,
        "ingredients": ["250 g hakket oksekød", "1 løg", "1 dåse hakkede tomater", "1 dåse kidneybønner",
                        "1 rød peberfrugt", "150 g ris", "1 tsk spidskommen", "salt og peber"],
        "method": "Brun kødet. Kog ris.",
    }
    assert extract_recipe("<html>Ingen opskrift</html>", "https://mad.dk/") is None


def test_update_fetches_new_recipes_once(tmp_path):
    sitemap = """<urlset><url><loc>https://mad.dk/opskrift/chili</loc></url>
        <url><loc>https://mad.dk/om-os</loc></url><url><loc>https://mad.dk/opskrift/tom</loc></url></urlset>"""
    pages = {"https://mad.dk/sitemap.xml": sitemap, "https://mad.dk/opskrift/chili": PAGE,
             "https://mad.dk/opskrift/tom": "<html></html>"}
    fetched = []

    def fetcher(url):
        fetched.append(url)
        return pages[url]

    lst = tmp_path / "opskrifter.txt"
    out = tmp_path / "opskrifter.json"
    lst.write_text("# kommentar\nsitemap: https://mad.dk/sitemap.xml /opskrift/\n", encoding="utf-8")
    assert update(lst, out, fetcher, delay=0) == {"recipes": 1, "added": 1, "failed": 0, "skipped": 1}
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [r["name"] for r in data["recipes"]] == ["Chili con carne & ris"]
    assert "method" not in data["recipes"][0]
    assert data["skipped"] == {"https://mad.dk/opskrift/tom": "ingen opskrift på siden"}
    # Næste gang hentes kun sitemappet
    fetched.clear()
    assert update(lst, out, fetcher, delay=0)["added"] == 0
    assert fetched == ["https://mad.dk/sitemap.xml"]
    # Fjernes linjen, fjernes opskrifterne
    lst.write_text("", encoding="utf-8")
    assert update(lst, out, fetcher, delay=0)["recipes"] == 0


def test_cli_recipes(tmp_path, monkeypatch, capsys):
    lst = tmp_path / "opskrifter.txt"
    lst.write_text("https://mad.dk/opskrift/chili\n", encoding="utf-8")
    monkeypatch.setattr("tilbudshenter.opskrifter.fetch", lambda url: PAGE)
    assert main(["opskrifter", "--liste", str(lst), "--ud", str(tmp_path / "o.json"), "--pause", "0"]) == 0
    assert "1 opskrifter i samlingen, 1 nye" in capsys.readouterr().out


def test_only_dinners():
    assert is_dinner({"name": "Boller i karry", "category": "Aftensmad"})
    assert is_dinner({"name": "Farsbrød med kartofler"})
    assert not is_dinner({"name": "Chokoladekage"})
    assert not is_dinner({"name": "Bananbrød", "category": "Bagværk"})
    assert not is_dinner({"name": "Ovnbagt rodfrugter", "category": "Tilbehør"})
