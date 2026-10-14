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
    assert veg.kind == "vegetar" and "porrer" in [i.name for i in veg.items if i.main]


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
    assert update(lst, out, fetcher, delay=0) == {"recipes": 1, "added": 1, "failed": 0, "skipped": 1,
                                                     "sites": {"mad.dk": 1}}
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


def test_salads_need_a_main_course_category():
    assert not is_dinner({"name": "Spidskålssalat med tomater på 5 minutter", "category": "Salat"})
    assert not is_dinner({"name": "Asiatisk salat", "category": "Salater, Frokost, Madpakke"})
    assert is_dinner({"name": "Grøn salat med laks", "category": "Salater, Hovedretter, Aftensmad"})
    assert is_dinner({"name": "Chili con carne", "category": ""})


def test_only_dinners():
    assert is_dinner({"name": "Boller i karry", "category": "Aftensmad"})
    assert is_dinner({"name": "Farsbrød med kartofler"})
    assert not is_dinner({"name": "Chokoladekage"})
    assert not is_dinner({"name": "Bananbrød", "category": "Bagværk"})
    assert not is_dinner({"name": "Ovnbagt rodfrugter", "category": "Tilbehør"})


def test_extract_microdata():
    # Som Valdemarsro: kun en artikel i JSON-LD, opskriften står som microdata
    page = """<html><head><title>Chili con carne - Valdemarsro</title>
    <script type="application/ld+json">{"@graph": [{"@type": "Article", "headline": "Chili"}]}</script></head>
    <body><div itemscope itemtype="https://schema.org/Recipe"><h1>Chili con carne</h1>
    <meta itemprop="recipeYield" content="4 personer"><meta itemprop="totalTime" content="PT45M">
    <ul><li itemprop="recipeIngredient">500 g hakket oksekød</li>
    <li class="ing" itemprop="recipeIngredient"><span>1</span> løg</li></ul>
    <div itemprop="recipeInstructions"><p>Brun kødet.</p></div></div></body></html>"""
    data = extract_recipe(page, "https://valdemarsro.dk/chili")
    assert data["name"] == "Chili con carne" and data["persons"] == 4 and data["minutes"] == 45
    assert data["ingredients"] == ["500 g hakket oksekød", "1 løg"]
    assert data["method"] == "Brun kødet."


def test_extract_embedded_json():
    # Som Arla: opskriften ligger i sidens egne data, ikke i et ld+json-felt
    page = """<html><head><meta property="og:title" content="Lasagne | Arla"></head><body>
    <script>window.__DATA__ = {"page": {"type": "recipe", "recipe": {"@type": "Recipe", "id": 7,
      "recipeCategory": "Frokost, Aftensmad", "info": {"x": 1},
      "recipeIngredient": ["300 g hakket oksekød", "1 løg"], "recipeYield": "4"}}};</script>
    <script>var s = "{\\"recipeIngredient\\":[\\"2 gulerødder\\"]}";</script></body></html>"""
    data = extract_recipe(page, "https://arla.dk/lasagne")
    assert data["name"] == "Lasagne" and data["category"] == "Frokost, Aftensmad"
    assert data["ingredients"] == ["300 g hakket oksekød", "1 løg"]
    escaped = page.split("<script>window")[0] + '<script>var s = "{\\"name\\":\\"Suppe\\",\\"recipeIngredient\\":[\\"2 gulerødder\\"]}";</script>'
    assert extract_recipe(escaped, "https://arla.dk/suppe")["ingredients"] == ["2 gulerødder"]


def test_old_collection_retries_skipped_pages(tmp_path):
    lst = tmp_path / "opskrifter.txt"
    out = tmp_path / "opskrifter.json"
    lst.write_text("https://mad.dk/opskrift/chili\n", encoding="utf-8")
    out.write_text(json.dumps({"recipes": [], "skipped": {"https://mad.dk/opskrift/chili": "ingen opskrift på siden"}}),
                   encoding="utf-8")
    assert update(lst, out, lambda url: PAGE, delay=0)["added"] == 1
    assert json.loads(out.read_text(encoding="utf-8"))["version"] >= 2


def test_sitemaps_from_robots_and_index(tmp_path):
    pages = {
        "https://mad.dk/robots.txt": "User-agent: *\nSitemap: https://mad.dk/sitemap_index.xml\n",
        "https://mad.dk/sitemap_index.xml": """<sitemapindex><sitemap><loc>https://mad.dk/category-sitemap.xml</loc></sitemap>
            <sitemap><loc>https://mad.dk/page-sitemap.xml</loc></sitemap>
            <sitemap><loc>https://mad.dk/post-sitemap.xml</loc></sitemap></sitemapindex>""",
        "https://mad.dk/post-sitemap.xml": """<urlset><url><loc>https://mad.dk/</loc></url>
            <url><loc>https://mad.dk/chili/</loc></url><url><loc>https://mad.dk/kategori/aftensmad/</loc></url>
            <url><loc>https://mad.dk/gryde/</loc></url><url><loc>https://mad.dk/suppe/</loc></url></urlset>""",
        "https://mad.dk/chili/": PAGE, "https://mad.dk/gryde/": PAGE, "https://mad.dk/suppe/": PAGE,
        "https://andet.dk/ret": PAGE,
    }
    fetched = []

    def fetcher(url):
        fetched.append(url)
        return pages[url]

    lst = tmp_path / "opskrifter.txt"
    out = tmp_path / "opskrifter.json"
    lst.write_text("sitemap: https://mad.dk/\nhttps://andet.dk/ret\n", encoding="utf-8")
    # Højst to nye sider pr. kørsel, skiftevis fra hver linje
    assert update(lst, out, fetcher, delay=0, max_new=2) == {
        "recipes": 2, "added": 2, "failed": 0, "skipped": 0, "pending": 2,
        "sites": {"mad.dk": 1, "andet.dk": 1}}
    assert "https://mad.dk/category-sitemap.xml" not in fetched and "https://mad.dk/page-sitemap.xml" not in fetched
    assert [r["url"] for r in json.loads(out.read_text(encoding="utf-8"))["recipes"]] == [
        "https://mad.dk/chili/", "https://andet.dk/ret"]
    assert update(lst, out, fetcher, delay=0, max_new=2)["recipes"] == 4


def test_sites_are_fetched_side_by_side_with_a_cap_per_site(tmp_path):
    # Sitemappet ligger på www.mad.dk, men opskrifterne på mad.dk
    pages = {
        "https://www.mad.dk/robots.txt": "Sitemap: https://www.mad.dk/sitemap.xml\n",
        "https://www.mad.dk/sitemap.xml": "<urlset>" + "".join(
            f"<url><loc>https://mad.dk/ret{i}/</loc></url>" for i in range(5)) + "</urlset>",
        **{f"https://mad.dk/ret{i}/": PAGE for i in range(5)},
        "https://andet.dk/ret": PAGE,
    }
    lst = tmp_path / "opskrifter.txt"
    out = tmp_path / "opskrifter.json"
    lst.write_text("sitemap: https://www.mad.dk/\nhttps://andet.dk/ret\n", encoding="utf-8")
    result = update(lst, out, pages.__getitem__, delay=0, per_site=2)
    assert result["sites"] == {"mad.dk": 2, "andet.dk": 1} and result["pending"] == 3
    assert update(lst, out, pages.__getitem__, delay=0, per_site=2)["sites"] == {"mad.dk": 4, "andet.dk": 1}


def test_addresses_with_danish_letters_can_be_fetched():
    from tilbudshenter.opskrifter import _ascii_url

    assert _ascii_url("https://www.opskrifter.dk/opskrift/447-kødsauce") == "https://www.opskrifter.dk/opskrift/447-k%C3%B8dsauce"
    assert _ascii_url("https://mad.dk/beh%c3%b8ver/?side=2") == "https://mad.dk/beh%c3%b8ver/?side=2"


def test_recipes_and_new_pages_are_fetched_first(tmp_path):
    xml = """<urlset>
      <url><loc>https://mad.dk/gammelt-blogindlaeg-fra-2012/</loc><lastmod>2012-05-01</lastmod></url>
      <url><loc>https://mad.dk/fisk/</loc><lastmod>2026-01-01</lastmod></url>
      <url><loc>https://mad.dk/kylling-i-fad-med-groent/</loc><lastmod>2025-03-01</lastmod></url>
    </urlset>"""
    pages = {"https://mad.dk/sitemap.xml": xml}
    lst = tmp_path / "opskrifter.txt"
    lst.write_text("sitemap: https://mad.dk/sitemap.xml\n", encoding="utf-8")
    fetched = []

    def fetcher(url):
        fetched.append(url)
        return pages.get(url, PAGE)

    update(lst, tmp_path / "opskrifter.json", fetcher, delay=0)
    assert fetched[1:] == ["https://mad.dk/kylling-i-fad-med-groent/", "https://mad.dk/gammelt-blogindlaeg-fra-2012/",
                           "https://mad.dk/fisk/"]
