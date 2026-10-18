"""Kilde: REMA 1000's webshop - normalpriser på hele sortimentet.

Tilbudsaviserne viser kun varer på tilbud. REMA 1000's offentlige
produkt-API (det samme som shop.rema1000.dk bruger) har prisen på alle
varer, også dem der ikke er på tilbud, med pris pr. kg eller liter. Den
bruges som normalpris i madplanen og ved tilbuddene.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from .base import SourceError

API_BASE = "https://api.digital.rema1000.dk/api/v3"
PAGE_SIZE = 100
MAX_PAGES = 300
USER_AGENT = "Tilbudshenter/0.1 (+https://github.com/simonhansen8/tilbudshenter)"


@dataclass
class ShelfPrice:
    """En vares almindelige hyldepris (uden tilbud) i en kæde."""

    dealer: str
    name: str
    underline: str  # fx "1 LTR. / REMA 1000"
    price: float
    unit: str | None  # "kg", "l" eller "stk" for enhedsprisen
    unit_price: float | None
    department: str = ""
    organic: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ShelfPrice":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


_UNITS = {"kg": "kg", "kilo": "kg", "ltr": "l", "liter": "l", "l": "l", "stk": "stk", "styk": "stk"}


def shelf_price(product: dict) -> ShelfPrice | None:
    """Normalprisen fra et produkt i API'et, eller None hvis varen kun har en
    kampagnepris (så kendes normalprisen ikke)."""
    prices = [p for p in product.get("prices") or [] if p.get("price")]
    normal = [p for p in prices if not p.get("is_campaign") and not p.get("is_advertised")]
    if not normal:
        return None
    p = min(normal, key=lambda p: p["price"])
    unit = _UNITS.get(str(p.get("compare_unit") or "").strip().lower().rstrip("."))
    unit_price = float(p["compare_unit_price"]) if unit and p.get("compare_unit_price") else None
    labels = {str(label.get("name", "")).casefold() for label in product.get("labels") or []}
    return ShelfPrice(
        dealer="REMA 1000",
        name=str(product.get("name") or "").strip(),
        underline=str(product.get("underline") or "").strip(),
        price=float(p["price"]),
        unit=unit if unit_price else None,
        unit_price=unit_price,
        department=str((product.get("department") or {}).get("name") or ""),
        organic="økologi" in labels,
    )


def _get(url: str, retries: int = 3) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.load(res)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise SourceError(f"REMA 1000 svarede ikke: {exc}") from exc
            time.sleep(2 ** attempt)
    raise SourceError("REMA 1000 svarede ikke")


def fetch_shelf_prices() -> list[ShelfPrice]:
    """Hele sortimentet med normalpriser. Fejler med SourceError."""
    result: list[ShelfPrice] = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(f"{API_BASE}/products?per_page={PAGE_SIZE}&page={page}&include=department")
        products = data.get("data") or []
        result.extend(p for p in map(shelf_price, products) if p)
        meta = (data.get("meta") or {}).get("pagination") or data.get("meta") or {}
        last = meta.get("total_pages") or meta.get("last_page")
        if not products or (last and page >= int(last)):
            break
    if not result:
        raise SourceError("REMA 1000 sendte ingen varer")
    return result
