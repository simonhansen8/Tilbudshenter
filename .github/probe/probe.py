# Midlertidig: henter REMA 1000's sortiment fra GitHub Actions
import json, urllib.request
from tilbudshenter.sources.rema import fetch_shelf_prices, API_BASE
raw = json.load(urllib.request.urlopen(urllib.request.Request(f"{API_BASE}/products?per_page=100&page=1", headers={"User-Agent": "x"})))
print("META", json.dumps({k: v for k, v in raw.items() if k != "data"})[:1500])
print("PRICES", json.dumps([p.get("prices") for p in raw["data"][:40] if len(p.get("prices") or []) > 1])[:3000])
prices = fetch_shelf_prices()
print("COUNT", len(prices))
json.dump([p.to_dict() for p in prices], open(".github/probe/rema.json", "w"), ensure_ascii=False)
