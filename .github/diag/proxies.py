"""Midlertidig: kan r.jina.ai give os opskriften? (fjernes igen)"""
import re, time, urllib.request
from tilbudshenter.opskrifter import extract_recipe

ORIGIN = "https://simonhansen8.github.io"

def get(url, headers):
    req = urllib.request.Request(url, headers={"Origin": ORIGIN, **headers})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, dict(r.headers), r.read(3_000_000).decode("utf-8", "replace"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(300).decode("utf-8", "replace"), time.time() - t
    except Exception as e:
        return None, {}, repr(e), time.time() - t

for target in ["https://madenimitliv.dk/groentsagslasagne/", "https://www.valdemarsro.dk/lasagne/", "https://www.arla.dk/opskrifter/lasagne/",
               "https://www.dr.dk/mad/opskrift/lasagne"]:
    print("\n==", target)
    for name, h in {"html": {"X-Return-Format": "html"}, "html+direct": {"X-Return-Format": "html", "X-Engine": "direct"},
                    "html+nocache": {"X-Return-Format": "html", "X-No-Cache": "true"},
                    "text": {}}.items():
        status, hd, body, secs = get(f"https://r.jina.ai/{target}", h)
        rec = extract_recipe(body, target) if status == 200 else None
        i = body.lower().find("ngrediens")
        print(f"{name:13} status={status} acao={hd.get('Access-Control-Allow-Origin')} expose={hd.get('Access-Control-Allow-Headers')} len={len(body)} {secs:.1f}s ldjson={'ld+json' in body} itemprop={'recipeIngredient' in body}"
              f" recipe={'JA ' + rec['name'] + ' (' + str(len(rec['ingredients'])) + ')' if rec else 'nej'}")
        if name == "text":
            print("   ", repr(body[max(0, i - 100):i + 700]))
    # preflight: tillader jina headeren X-Return-Format fra github.io?
    req = urllib.request.Request(f"https://r.jina.ai/{target}", method="OPTIONS", headers={"Origin": ORIGIN,
        "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-return-format"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("preflight", r.status, r.headers.get("Access-Control-Allow-Headers"), r.headers.get("Access-Control-Allow-Origin"))
    except Exception as e:
        print("preflight fejl", e)
