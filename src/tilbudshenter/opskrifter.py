"""Opskrifter fra madsider.

Næsten alle madsider beskriver deres opskrifter med schema.org/Recipe
(JSON-LD), så Google kan vise dem. Det bruger andre madplansapps også,
når man "gemmer" en opskrift fra nettet. Herfra hentes navn, antal
personer, tid og ingredienslisten; fremgangsmåden bliver på madsiden, og
madplanen linker til den.

Listen over madsider står i opskrifter.txt: én adresse pr. linje, enten en
opskrift eller et sitemap (``sitemap: https://...``), hvorfra de første
opskrifter tages. Resultatet gemmes i data/opskrifter.json, så hver side
kun hentes én gang.
"""

from __future__ import annotations

import gzip
import html as htmllib
import json
import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

from .comparison import _has_word, _tokens
from .mealplan import recipe_from_lines

log = logging.getLogger(__name__)

USER_AGENT = "Tilbudshenter/0.1 (madplan; https://github.com/simonhansen8/Tilbudshenter)"
MAX_BYTES = 3_000_000
DEFAULT_JSON = Path(__file__).parent / "data" / "opskrifter.json"
SITEMAP_LIMIT = 1000
# Højst så mange nye sider pr. kørsel, så siden stadig bygges hurtigt;
# resten hentes de næste gange. Madsiderne hentes samtidig, men hver
# madside kun én side ad gangen.
NEW_PER_RUN = 1500
PER_SITE_PER_RUN = 150
# Sitemaps og sider, der ikke er opskrifter
SKIP_SITEMAPS = ("category", "categories", "kategori", "tag", "author", "forfatter", "page-sitemap", "attachment",
                 "product", "produkt", "video", "image", "news", "nyhed")
GOOD_SITEMAPS = ("opskrift", "recipe", "post")
NOT_RECIPES = ("/kategori/", "/category/", "/tag/", "/author/", "/forfatter/", "/page/", "/side/", "/soeg", "/search")
# Hæves, når opskrifter kan læses fra flere slags sider, så de sider, der
# blev sprunget over før, prøves igen
VERSION = 4


def _ascii_url(url: str) -> str:
    """Adressen med æ, ø og å kodet som %C3%A6 osv., som urllib kræver."""
    s = urlsplit(url)
    return urlunsplit((s.scheme, s.netloc.encode("idna").decode(), quote(s.path, safe="/%:@!$&'()*+,;=-._~"),
                       quote(s.query, safe="=&%+:/?,;"), ""))


def fetch(url: str, timeout: float = 20) -> str:
    req = urllib.request.Request(_ascii_url(url), headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = res.read(MAX_BYTES)
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        charset = res.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace")


# -- Læsning af opskriften -------------------------------------------------
_LD_JSON = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def _is_recipe(node: dict) -> bool:
    t = node.get("@type")
    return t == "Recipe" or (isinstance(t, list) and "Recipe" in t)


def _find_recipe(node) -> dict | None:
    if isinstance(node, list):
        for n in node:
            if (found := _find_recipe(n)) is not None:
                return found
    elif isinstance(node, dict):
        if _is_recipe(node):
            return node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node and (found := _find_recipe(node[key])) is not None:
                return found
    return None


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value] if value else []


def _text(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or ""
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", "" if value is None else str(value)))
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", text)).strip()


def _minutes(value) -> int:
    """ISO 8601-varighed som "PT1H30M" i minutter."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?)?", str(value or "").strip())
    if not m:
        return 0
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


def _persons(value) -> int:
    for v in value if isinstance(value, list) else [value]:
        if m := re.search(r"\d+", str(v)):
            return int(m.group())
    return 4


def _steps(value) -> list[str]:
    if isinstance(value, str):
        return [s for s in (_text(p) for p in re.split(r"\n+", value)) if s]
    steps: list[str] = []
    for v in value or []:
        if isinstance(v, dict) and v.get("itemListElement"):
            steps += _steps(v["itemListElement"])
        elif isinstance(v, (dict, str)) and (t := _text(v)):
            steps.append(t)
    return steps


def _ld_json_nodes(page: str):
    for block in _LD_JSON.findall(page):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        if (node := _find_recipe(data)) is not None:
            yield node


def _embedded_nodes(page: str):
    """Opskrifter i JSON, der ligger andre steder på siden (fx Arla).

    Nogle sider har opskriften i sidens egne data i stedet for et
    ld+json-felt. Fra hvert "recipeIngredient" går vi baglæns til den
    krølleparentes, hvor objektet med listen begynder.
    """
    texts = [page]
    if '\\"recipeIngredient\\"' in page:  # JSON inde i en JavaScript-streng
        texts.append(page.replace('\\"', '"'))
    decoder = json.JSONDecoder()
    for text in texts:
        for m in re.finditer(r'"recipeIngredient"\s*:', text):
            start, tries = m.start(), 0
            while tries < 300 and (start := text.rfind("{", max(0, m.start() - 50_000), start)) >= 0:
                tries += 1
                try:
                    node, _ = decoder.raw_decode(text, start)
                except json.JSONDecodeError:
                    continue
                if isinstance(node, dict) and "recipeIngredient" in node:
                    yield node
                    break


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.IGNORECASE)
    return next((g for g in m.groups() if g is not None), "") if m else None


def _itemprops(page: str, prop: str) -> list[str]:
    """Værdierne af et microdata-felt: ``<li itemprop="recipeIngredient">``."""
    values = []
    pattern = rf'<(\w+)\b[^>]*\bitemprop\s*=\s*["\']?[^"\'>]*\b{prop}\b[^>]*>'
    for m in re.finditer(pattern, page, re.IGNORECASE):
        tag = m.group(0)
        content = _attr(tag, "content")
        if content is None and m.group(1).lower() not in ("meta", "link"):
            end = re.search(rf"</{m.group(1)}\s*>", page[m.end():], re.IGNORECASE)
            content = page[m.end(): m.end() + end.start()] if end else ""
        values.append(content or "")
    return values


def _page_title(page: str) -> str:
    for pattern in (r'<meta[^>]+property=["\']og:title["\'][^>]*>', r"<h1\b[^>]*>(.*?)</h1>", r"<title\b[^>]*>(.*?)</title>"):
        if m := re.search(pattern, page, re.IGNORECASE | re.DOTALL):
            title = _text(_attr(m.group(0), "content") if pattern.startswith("<meta") else m.group(1))
            if title := re.split(r"\s+[-|–]\s+", title)[0].strip():
                return title
    return ""


def _microdata_node(page: str) -> dict | None:
    """Opskrifter beskrevet med microdata i selve HTML'en (fx Valdemarsro)."""
    lines = _itemprops(page, "recipeIngredient") or _itemprops(page, "ingredients")
    if not lines:
        return None
    first = lambda prop: next(iter(_itemprops(page, prop)), "")  # noqa: E731
    return {
        "name": _page_title(page), "recipeIngredient": lines,
        "recipeYield": first("recipeYield"), "totalTime": first("totalTime"),
        "prepTime": first("prepTime"), "cookTime": first("cookTime"),
        "recipeCategory": _itemprops(page, "recipeCategory"),
        "recipeInstructions": _itemprops(page, "recipeInstructions") or _itemprops(page, "text"),
    }


def extract_recipe(page: str, url: str) -> dict | None:
    """Opskriften på en side, eller None hvis siden ikke har én.

    Først schema.org/Recipe som JSON-LD, så som JSON andre steder på siden
    og til sidst som microdata. Fremgangsmåden ("method") kommer med, men
    gemmes kun i brugerens egne opskrifter, ikke i den fælles samling.
    """
    nodes = [*_ld_json_nodes(page), *_embedded_nodes(page)]
    if (node := _microdata_node(page)) is not None:
        nodes.append(node)
    for node in nodes:
        lines = [t for t in (_text(i) for i in _as_list(node.get("recipeIngredient") or node.get("ingredients"))) if t]
        name = _text(node.get("name")) or _page_title(page)
        if not name or not lines:
            continue
        minutes = _minutes(node.get("totalTime")) or _minutes(node.get("prepTime")) + _minutes(node.get("cookTime"))
        category = ", ".join(t for t in (_text(c) for c in _as_list(node.get("recipeCategory"))) if t)
        return {
            "url": url, "name": name[:80], "category": category[:80],
            "persons": _persons(node.get("recipeYield")), "minutes": minutes,
            "ingredients": lines[:40], "method": " ".join(_steps(node.get("recipeInstructions")))[:4000],
        }
    return None


# Opskrifter, der ikke er aftensmad (et sitemap har også kager og drinks)
NOT_DINNER = ["kage", "kager", "muffin", "cookie", "småkage", "brød ", "dessert", "desserter", "is ", "smoothie",
              "drink", "cocktail", "marmelade", "syltetøj", "dressing", "snack", "konfekt", "chokolade", "grød",
              "bagværk", "drikke", "tilbehør", "forret", "forretter", "morgenmad"]


# Kategorier for salater og frokost: kun aftensmad, når madsiden også kalder
# retten en hovedret, fx "Salater, Hovedretter, Aftensmad"
SIDE_CATEGORIES = ["salat", "salater", "frokost", "madpakke", "tapas", "brunch"]
MAIN_CATEGORIES = ["aftensmad", "hovedret", "hovedretter", "middag", "aftensretter"]


def is_dinner(recipe: dict) -> bool:
    text = f"{recipe['name']} {recipe.get('category', '')}"
    if any(_has_word(_tokens(text), w) for w in NOT_DINNER):
        return False
    cats = _tokens(recipe.get("category") or "")
    return not (any(_has_word(cats, w) for w in SIDE_CATEGORIES) and not any(_has_word(cats, w) for w in MAIN_CATEGORIES))


def sitemap_urls(xml: str) -> list[str]:
    return [htmllib.unescape(u.strip()) for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.DOTALL)]


def _looks_like_recipe(url: str) -> bool:
    """Opskrifter har lange navne ("kylling-i-fad-med-groent"), oversigter
    korte ("fisk-opskrifter/laks")."""
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].count("-") >= 2


def _newest_first(xml: str, urls: list[str]) -> list[str]:
    """Siderne med den nyeste <lastmod> først. Mange sitemaps står ældst
    først, og de ældste sider er ofte blogindlæg."""
    lastmod = {
        htmllib.unescape(loc.strip()): mod.strip()
        for loc, mod in re.findall(r"<loc>\s*(.*?)\s*</loc>\s*<lastmod>\s*(.*?)\s*</lastmod>", xml, re.DOTALL)
    }
    return sorted(urls, key=lambda u: lastmod.get(u, ""), reverse=True)


# -- Samlingen ---------------------------------------------------------
def read_list(path: Path) -> list[str]:
    """Linjerne i opskrifter.txt uden kommentarer."""
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _site(url: str) -> str:
    """Madsiden bag en adresse; www.mummum.dk og mummum.dk er den samme."""
    return urlparse(url).netloc.lower().removeprefix("www.")


def _sitemaps(url: str, fetcher) -> list[str]:
    """Sitemaps for en linje. Står der kun madsidens adresse, findes de i robots.txt."""
    p = urlparse(url)
    if p.path not in ("", "/"):
        return [url]
    base = f"{p.scheme}://{p.netloc}"
    try:
        found = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", fetcher(base + "/robots.txt"))
    except Exception:  # noqa: BLE001 - så prøves de almindelige adresser
        found = []
    return found or [base + "/sitemap_index.xml", base + "/sitemap.xml", base + "/wp-sitemap.xml"]


def _sitemap_pages(url: str, fetcher, ok, enough: int, depth: int = 0) -> list[str]:
    """Siderne i et sitemap, der består ``ok``. Et sitemap-indeks peger på flere
    sitemaps; dem med opskrifter læses først, og kategorier o.l. springes over."""
    xml = fetcher(url)
    urls = sitemap_urls(xml)
    subs = [u for u in urls if u.split("?")[0].endswith((".xml", ".xml.gz"))]
    pages = _newest_first(xml, [u for u in urls if u not in subs and ok(u)])
    if depth < 2:
        subs = [u for u in subs if not any(w in u.lower() for w in SKIP_SITEMAPS)]
        subs.sort(key=lambda u: not any(w in u.lower() for w in GOOD_SITEMAPS))
        for sub in subs:
            if len(pages) >= enough:
                break
            try:
                pages += _sitemap_pages(sub, fetcher, ok, enough - len(pages), depth + 1)
            except Exception as exc:  # noqa: BLE001
                log.warning("Kunne ikke læse %s: %s", sub, exc)
    return pages


def _expand(line: str, fetcher, limit: int, known: set[str], skipped: set[str]) -> list[str]:
    """Adresserne på en linje.

    Et sitemap giver op til ``limit`` opskrifter: dem, der allerede er
    hentet derfra, og så nye, til der er nok. Samlingen skifter derfor ikke,
    når madsiden lægger nye opskrifter øverst.
    """
    m = re.match(r"sitemap:\s*(\S+)(?:\s+(\S+))?", line, re.IGNORECASE)
    if not m:
        return [line]
    url, must = m.group(1), m.group(2) or ""
    site = _site(url)
    have = [u for u in known if _site(u) == site and must in u]
    if len(have) >= limit:
        return have[:limit]

    def ok(u: str) -> bool:
        p = urlparse(u)
        return must in u and _site(u) == site and p.path.strip("/") != "" and not any(w in p.path for w in NOT_RECIPES)

    urls: list[str] = []
    errors = []
    for sm in _sitemaps(url, fetcher):
        try:
            urls += _sitemap_pages(sm, fetcher, ok, 5 * limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        if len(urls) >= 5 * limit:
            break
    if not urls and errors:
        raise errors[0]
    # Sider, der ligner opskrifter, først; oversigter og artikler til sidst
    new = sorted((u for u in dict.fromkeys(urls) if u not in known), key=lambda u: not _looks_like_recipe(u))
    tried = [u for u in new if u in skipped]
    fresh = [u for u in new if u not in skipped][: limit - len(have)]
    return have + fresh + tried


def _fetch_all(urls: list[str], fetcher, delay: float) -> dict[str, str | Exception]:
    """Henter siderne: madsiderne samtidig, men hver madside én side ad gangen
    med ``delay`` sekunders pause, så ingen madside belastes."""
    by_site: dict[str, list[str]] = {}
    for u in urls:
        by_site.setdefault(_site(u), []).append(u)

    def one_site(site_urls: list[str]) -> dict[str, str | Exception]:
        out: dict[str, str | Exception] = {}
        for i, u in enumerate(site_urls):
            if i and delay:
                time.sleep(delay)
            try:
                out[u] = fetcher(u)
            except Exception as exc:  # noqa: BLE001
                out[u] = exc
        return out

    pages: dict[str, str | Exception] = {}
    if by_site:
        with ThreadPoolExecutor(min(16, len(by_site))) as pool:
            for part in pool.map(one_site, by_site.values()):
                pages.update(part)
    return pages


def update(list_path: Path, json_path: Path = DEFAULT_JSON, fetcher=None, delay: float = 1.0,
           limit: int = SITEMAP_LIMIT, max_new: int = NEW_PER_RUN, per_site: int = PER_SITE_PER_RUN) -> dict:
    """Henter de opskrifter i listen, der ikke er hentet før.

    Opskrifter, der er fjernet fra listen, fjernes også fra samlingen.
    Sider, der ikke kunne bruges, huskes, så de ikke hentes igen.
    """
    fetcher = fetcher or fetch
    old = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    known = {r["url"]: r for r in old.get("recipes", [])}
    skipped: dict[str, str] = dict(old.get("skipped", {})) if old.get("version", 1) >= VERSION else {}
    known_urls, skipped_urls = set(known), set(skipped)

    def expand(line: str) -> list[str]:
        try:
            return _expand(line, fetcher, limit, known_urls, skipped_urls)
        except Exception as exc:  # noqa: BLE001 - et dårligt sitemap må ikke stoppe resten
            # Behold det, der allerede er hentet, til sitemappet virker igen
            log.warning("Kunne ikke læse %s: %s", line, exc)
            parts = line.split()
            site = _site(parts[1] if parts[0].lower() == "sitemap:" and len(parts) > 1 else parts[0])
            return [u for u in known if _site(u) == site]

    # Sitemaps fra alle madsider læses samtidig
    with ThreadPoolExecutor(16) as pool:
        per_line = list(pool.map(expand, read_list(list_path)))
    # Skiftevis fra hver linje, så alle madsider får nye opskrifter, også når
    # der hentes højst NEW_PER_RUN sider
    wanted = [u for group in zip_longest(*per_line) for u in group if u]
    wanted = list(dict.fromkeys(wanted))
    new = [u for u in wanted if u not in known and u not in skipped and urlparse(u).scheme in ("http", "https")]
    fetch_now: list[str] = []
    count: dict[str, int] = {}
    for u in new:
        if len(fetch_now) < max_new and count.get(_site(u), 0) < per_site:
            fetch_now.append(u)
            count[_site(u)] = count.get(_site(u), 0) + 1
    pending = len(new) - len(fetch_now)
    pages = _fetch_all(fetch_now, fetcher, delay)
    recipes, added, failed = [], 0, 0
    for url in wanted:
        if url in known:
            # Reglerne for aftensmad kan være blevet skærpet siden
            if is_dinner(known[url]):
                recipes.append(known[url])
            else:
                skipped[url] = "ikke aftensmad"
            continue
        if url not in pages:
            continue
        page = pages[url]
        if isinstance(page, Exception):
            log.warning("Kunne ikke hente %s: %s", url, page)
            failed += 1
            continue
        found = extract_recipe(page, url)
        why = "ingen opskrift på siden"
        if found and not is_dinner(found):
            why = "ikke aftensmad"
        elif found:
            found.pop("method")
            recipe, why = recipe_from_lines("", found["name"], found["ingredients"], found["persons"])
            if recipe:
                recipes.append({**found, "fetched": datetime.now(timezone.utc).date().isoformat()})
                added += 1
                continue
        skipped[url] = why
        log.info("Springer %s over: %s", url, why)
    keep = set(wanted)
    data = {
        "version": VERSION,
        "recipes": recipes,
        "skipped": {u: w for u, w in sorted(skipped.items()) if u in keep},
    }
    if data != old:
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    result = {"recipes": len(recipes), "added": added, "failed": failed, "skipped": len(data["skipped"])}
    sites: dict[str, int] = {}
    for r in recipes:
        sites[_site(r["url"])] = sites.get(_site(r["url"]), 0) + 1
    result["sites"] = sites
    return {**result, "pending": pending} if pending else result
