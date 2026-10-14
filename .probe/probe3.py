"""Midlertidig: kører den rigtige hentning og viser tid og grunde pr. madside."""
import collections, json, shutil, sys, time
from pathlib import Path
from tilbudshenter import opskrifter as o

src = Path("src/tilbudshenter/data/opskrifter.json")
dst = Path("/tmp/samling.json")
shutil.copy(src, dst)
t0 = time.time()
orig_fetch_all, orig_expand = o._fetch_all, o._expand
def fetch_all(urls, fetcher, delay):
    print(f"udvidelse af sitemaps: {time.time() - t0:.0f} s; henter {len(urls)} sider", flush=True)
    c = collections.Counter(o._site(u) for u in urls); print(dict(c), flush=True)
    t1 = time.time(); r = orig_fetch_all(urls, fetcher, delay); print(f"hentning: {time.time() - t1:.0f} s", flush=True)
    return r
def expand(line, *a, **k):
    t = time.time(); r = orig_expand(line, *a, **k)
    if line.startswith("sitemap"): print(f"  {line[:60]}: {len(r)} adresser, {time.time() - t:.0f} s", flush=True)
    return r
o._fetch_all, o._expand = fetch_all, expand
res = o.update(Path("opskrifter.txt"), dst)
print({k: v for k, v in res.items() if k != "sites"}, res["sites"])
d = json.loads(dst.read_text())
why = collections.Counter((o._site(u), w.split(":")[0]) for u, w in d["skipped"].items())
for (s, w), n in sorted(why.items()): print(f"  {s:25} {w:30} {n}")
for s in ("hellofresh.dk", "femina.dk"):
    print(s, [(u, w) for u, w in d["skipped"].items() if o._site(u) == s][:15])
