"""Midlertidig: hvorfor opskrifter afvises, og hvordan sider uden fundet opskrift ser ud."""
import sys, re, collections, random
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, quote, urlsplit, urlunsplit
from tilbudshenter import opskrifter as o
from tilbudshenter import mealplan as m

def fetch(u):
    s = urlsplit(u)
    u = urlunsplit((s.scheme, s.netloc, quote(s.path, safe="/%:@!$&'()*+,;=-._~"), s.query, s.fragment))
    return o.fetch(u, timeout=20)

SITES = [l.split() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
N = 40

def probe(parts):
    base, must = parts[0], (parts[1] if len(parts) > 1 else "")
    site = o._site(base)
    ok = lambda u: must in u and o._site(u) == site and urlparse(u).path.strip("/") != "" and not any(w in urlparse(u).path for w in o.NOT_RECIPES)
    urls = []
    for s in o._sitemaps(base, fetch):
        try: urls += o._sitemap_pages(s, fetch, ok, 3000)
        except Exception: pass
        if len(urls) >= 3000: break
    urls = list(dict.fromkeys(urls))
    random.seed(1); sample = random.sample(urls, min(N, len(urls)))
    reasons = collections.Counter(); unknown = collections.Counter(); meat = collections.Counter(); notes = []
    norec = 0
    for u in sample:
        try: page = fetch(u)
        except Exception as e:
            reasons["fejl " + type(e).__name__] += 1; continue
        f = o.extract_recipe(page, u)
        if not f:
            reasons["ingen opskrift"] += 1
            if norec < 2 and len(page) > 5000:
                norec += 1
                low = page.lower()
                i = low.find("ingredien")
                notes.append(f"INGEN {u} len={len(page)} ld+json={low.count('ld+json')} recipe={page.count('Recipe')} "
                             f"itemprop={low.count('itemprop')} __next_data__={'__next_data__' in low} nuxt={'__nuxt' in low}\n"
                             f"   ...{re.sub(r'\\s+', ' ', page[max(0,i-200):i+500]) if i>=0 else ''}")
            continue
        if not o.is_dinner(f):
            reasons["ikke aftensmad"] += 1
            if len(notes) < 12: notes.append(f"IKKE {f['name'][:50]} | kat={f['category'][:60]}")
            continue
        r, why = m.recipe_from_lines("", f["name"], f["ingredients"], f["persons"])
        reasons["OK" if r else why.split(":")[0]] += 1
        for line in f["ingredients"]:
            amount, unit, text = m.parse_line(line)
            if text and not m.line_keys(text) and not m._has_any(text, m.PANTRY_WORDS):
                (meat if m.diet_flag(text) else unknown)[text.lower()[:40]] += 1
        if not r and len(notes) < 16:
            notes.append(f"AFVIST {f['name'][:40]} ({why[:60]}): {f['ingredients'][:10]}")
    return site, len(urls), reasons, unknown, meat, notes

with ThreadPoolExecutor(16) as ex:
    results = list(ex.map(probe, SITES))
tot_u = collections.Counter(); tot_m = collections.Counter()
for site, n, reasons, unknown, meat, notes in results:
    print(f"\n### {site} ({n} sider): {dict(reasons)}")
    for x in notes: print("  ", x[:900])
    tot_u.update(unknown); tot_m.update(meat)
print("\n=== UKENDTE VARER ===")
print(tot_u.most_common(250))
print("\n=== UKENDT KØD/FISK ===")
print(tot_m.most_common(120))
