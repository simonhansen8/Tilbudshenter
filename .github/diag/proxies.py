"""Midlertidig: kan de offentlige proxyer hente en opskrift? (fjernes igen)"""
import json, re, time, urllib.parse, urllib.request
from tilbudshenter.opskrifter import extract_recipe

ORIGIN = "https://simonhansen8.github.io"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"

def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"Origin": ORIGIN, "User-Agent": UA})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000).decode("utf-8", "replace")
            return r.status, r.headers.get("Access-Control-Allow-Origin"), body, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Access-Control-Allow-Origin"), e.read(300).decode("utf-8", "replace"), time.time() - t
    except Exception as e:
        return None, None, repr(e), time.time() - t

home = get("https://madenimitliv.dk/")[2]
urls = sorted(set(re.findall(r'https://madenimitliv\.dk/groentsags[^"\'<> ]+', home)))
print("fundne links:", urls[:5])
recipe = urls[0] if urls else "https://madenimitliv.dk/groentsagslasagne/"
for target in [recipe, "https://www.valdemarsro.dk/lasagne/", "https://www.arla.dk/opskrifter/lasagne/"]:
    q = urllib.parse.quote(target, safe="")
    cands = {
        "direct": target,
        "allorigins raw": f"https://api.allorigins.win/raw?url={q}",
        "allorigins get": f"https://api.allorigins.win/get?url={q}",
        "corsproxy.io": f"https://corsproxy.io/?url={q}",
        "codetabs": f"https://api.codetabs.com/v1/proxy?quest={q}",
        "cors.lol": f"https://api.cors.lol/?url={q}",
        "whateverorigin": f"https://whateverorigin.org/get?url={q}",
        "everyorigin": f"https://everyorigin.jwvbremen.nl/get?url={q}",
        "corsproxy.org": f"https://corsproxy.org/?url={q}",
        "thingproxy": f"https://thingproxy.freeboard.io/fetch/{target}",
        "jina html": f"https://r.jina.ai/{target}",
    }
    print("\n==", target)
    for name, u in cands.items():
        status, acao, body, secs = get(u)
        if name.endswith("get") or name in ("whateverorigin", "everyorigin"):
            try: body = json.loads(body).get("contents") or body
            except Exception: pass
        rec = extract_recipe(body, target) if status == 200 else None
        print(f"{name:16} status={status} acao={acao} len={len(body)} {secs:.1f}s recipe={'JA ' + rec['name'] + ' (' + str(len(rec['ingredients'])) + ' linjer)' if rec else 'nej'}"
              + ("" if status == 200 else f" | {body[:120]!r}"))
