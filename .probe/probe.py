"""Midlertidig: afprøver madsider fra GitHub Actions."""
import sys, re, traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from tilbudshenter import opskrifter as o
from tilbudshenter.mealplan import recipe_from_lines

SITES = [l.split() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]

def fetch(u):
    return o.fetch(u, timeout=20)

def probe(parts):
    base, must = parts[0], (parts[1] if len(parts) > 1 else "")
    host = urlparse(base).netloc
    out = []
    try:
        try:
            r = fetch(f"{urlparse(base).scheme}://{host}/robots.txt")
            sm = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r)
            out.append(f"robots ok, {len(sm)} sitemaps: {' '.join(sm[:4])}")
        except Exception as e:
            out.append(f"robots FEJL {e!r:.80}")
        def ok(u):
            p = urlparse(u)
            return must in u and p.netloc.removeprefix("www.") == host.removeprefix("www.") and p.path.strip("/") != "" and not any(w in p.path for w in o.NOT_RECIPES)
        urls, errs = [], []
        for s in o._sitemaps(base, fetch):
            try:
                urls += o._sitemap_pages(s, fetch, ok, 3000)
            except Exception as e:
                errs.append(f"{s}: {e!r:.80}")
            if len(urls) >= 3000:
                break
        urls = list(dict.fromkeys(urls))
        out.append(f"{len(urls)} sider i sitemap; fejl: {errs[:2]}")
        if not urls:
            # se hvad forsiden har af links
            try:
                page = fetch(base)
                links = set(re.findall(r'href="(https?://[^"]+|/[^"]+)"', page))
                out.append(f"forside {len(page)} tegn, {len(links)} links, eks: {sorted(links)[:8]}")
            except Exception as e:
                out.append(f"forside FEJL {e!r:.80}")
            return host, 0, 0, out
        step = max(1, len(urls) // 12)
        sample = urls[::step][:12]
        good = rec = 0
        for u in sample:
            try:
                f = o.extract_recipe(fetch(u), u)
            except Exception as e:
                out.append(f"  {u} FEJL {e!r:.60}")
                continue
            if not f:
                out.append(f"  {u}: ingen opskrift")
                continue
            rec += 1
            why = "ikke aftensmad"
            if o.is_dinner(f):
                r, why = recipe_from_lines("", f["name"], f["ingredients"], f["persons"])
                if r:
                    good += 1
                    why = "OK"
            out.append(f"  {u}: {f['name'][:40]} -> {why}")
        return host, len(urls), (rec, good, len(sample)), out
    except Exception:
        return host, -1, 0, out + [traceback.format_exc()[-300:]]

with ThreadPoolExecutor(16) as ex:
    results = list(ex.map(probe, SITES))
print("=== OVERSIGT ===")
for host, n, s, _ in results:
    print(f"{host:35} sider={n:5}  opskrift/brugbar/prøvet={s}")
for host, n, s, out in results:
    print(f"\n### {host}")
    print("\n".join(out))
