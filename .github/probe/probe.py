# Midlertidig: tester hvilke webshops der svarer fra GitHub Actions
import json, sys, urllib.request, urllib.parse
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
q = urllib.parse.quote("letmælk")
URLS = [
    ("rema_products", f"https://api.digital.rema1000.dk/api/v3/products?per_page=2&page=1&include=department", {}),
    ("rema_search", f"https://api.digital.rema1000.dk/api/v3/products?search={q}&per_page=2", {}),
    ("rema_depts", "https://api.digital.rema1000.dk/api/v3/departments", {}),
    ("nemlig_search", f"https://www.nemlig.com/webapi/s/0/1/0/Search/Search?query={q}&take=3&skip=0&recipeCount=0", {"Accept": "application/json"}),
    ("nemlig_home", "https://www.nemlig.com/", {}),
    ("bilkatogo", f"https://www.bilkatogo.dk/s/?query={q}", {}),
    ("salling", f"https://api.sallinggroup.com/v1-beta/product-suggestions/relevant-products?query={q}", {}),
    ("coop_api", "https://api.cl.coop.dk/productapi/v1/product/24165", {}),
    ("coop_shop", f"https://shop.coop.dk/soeg?query={q}", {}),
    ("lidl", f"https://www.lidl.dk/q/search?q={q}", {}),
    ("netto", "https://www.netto.dk/", {}),
    ("foetex_hjem", f"https://hjem.foetex.dk/s/?query={q}", {}),
    ("openprices", "https://prices.openfoodfacts.org/api/v1/prices?currency=DKK&size=2", {}),
]
for name, url, headers in URLS:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(200000).decode("utf-8", "replace")
            print(f"=== {name} {r.status} {r.headers.get('content-type')}\n{body[:1500]}\n")
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            body = e.read(800).decode("utf-8", "replace")
        print(f"=== {name} ERROR {e!r}\n{body}\n")
