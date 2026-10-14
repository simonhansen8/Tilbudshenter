"""Kilde: Tjek (eTilbudsavis) - de danske dagligvarekæders tilbudsaviser.

Bruger Tjek's offentlige REST API (v2), som også ligger bag
etilbudsavis.dk. API'et returnerer aviser for et område samt de enkelte
tilbud med pris, førpris og mængde.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Iterator

from ..models import Catalog, Offer, normalize_unit
from .base import SourceError

API_BASE = "https://squid-api.tjek.com/v2"
PAGE_SIZE = 100
USER_AGENT = "Tilbudshenter/0.1 (+https://github.com/simonhansen8/tilbudshenter)"
WEB_BASE = "https://etilbudsavis.dk"


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for parse in (
        datetime.fromisoformat,
        lambda v: datetime.strptime(v, "%Y-%m-%dT%H:%M:%S%z"),
    ):
        try:
            return parse(value)
        except ValueError:
            continue
    return None


def _first(*values: Any) -> Any:
    return next((v for v in values if v not in (None, "")), None)


def parse_quantity(quantity: dict | None) -> tuple[float | None, str | None]:
    """Omregner Tjek's quantity-objekt til (mængde, SI-enhed)."""
    if not quantity:
        return None, None
    unit = quantity.get("unit") or {}
    size = (quantity.get("size") or {}).get("from")
    pieces = (quantity.get("pieces") or {}).get("from") or 1

    si = unit.get("si") or {}
    normalized = normalize_unit(si["symbol"]) if si.get("symbol") else None
    factor = si.get("factor")
    if normalized is None or factor is None:
        normalized = normalize_unit(unit.get("symbol") or "")
        if normalized is None:
            return None, None
        factor = normalized[1]
    si_unit = normalized[0]

    if si_unit == "stk":
        amount = size if size and size > 1 else pieces
    elif size:
        amount = size * float(factor) * pieces
    else:
        return None, None
    return (float(amount), si_unit) if amount and amount > 0 else (None, None)


def catalog_url(data: dict) -> str | None:
    """Avisen på etilbudsavis.dk, fx https://etilbudsavis.dk/Netto/tilbudsaviser/4_qLrKZB."""
    markets = (data.get("dealer") or {}).get("markets") or []
    slug = next((m.get("slug") for m in markets if m.get("country_code") == "DK" and m.get("slug")), None)
    if not slug or not data.get("id"):
        return None
    return f"{WEB_BASE}/{urllib.parse.quote(slug)}/tilbudsaviser/{urllib.parse.quote(str(data['id']))}"


def catalog_from_api(data: dict) -> Catalog:
    branding = data.get("branding") or {}
    dealer = data.get("dealer") or {}
    return Catalog(
        id=str(data["id"]),
        dealer=_first(branding.get("name"), dealer.get("name"), data.get("dealer_id"), "Ukendt"),
        label=data.get("label") or "",
        run_from=parse_datetime(data.get("run_from")),
        run_till=parse_datetime(data.get("run_till")),
        offer_count=data.get("offer_count"),
        url=catalog_url(data),
        dealer_id=data.get("dealer_id"),
    )


def image_box(url: str | None) -> tuple[float, float, float, float] | None:
    """Tilbuddets placering på avissiden (x1, y1, x2, y2 som brøkdele af
    siden), som står i billedets adresse (x1r=0.5&y1r=0.56&...)."""
    if not url:
        return None
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        box = tuple(float(query[k][0]) for k in ("x1r", "y1r", "x2r", "y2r"))
    except (KeyError, ValueError):
        return None
    return box  # type: ignore[return-value]


def paper_order(items: list[tuple[Offer, int | None, tuple | None]]) -> None:
    """Nummererer tilbuddene i den rækkefølge, de står i avisen: side for
    side, og på hver side række for række oppefra og hver række fra venstre.
    Et tilbud hører til samme række som det øverste i rækken, hvis det
    begynder over dettes midte."""
    pages: dict[int, list[tuple[Offer, tuple | None]]] = {}
    for offer, page, box in items:
        pages.setdefault(page if page is not None else 10**6, []).append((offer, box))
    order = 0
    for page in sorted(pages):
        placed = sorted((e for e in pages[page] if e[1]), key=lambda e: (e[1][1], e[1][0]))
        rows: list[list[tuple[Offer, tuple]]] = []
        for entry in placed:
            first = rows[-1][0][1] if rows else None
            if first and entry[1][1] < (first[1] + first[3]) / 2:
                rows[-1].append(entry)
            else:
                rows.append([entry])
        ordered = [e for row in rows for e in sorted(row, key=lambda e: e[1][0])]
        ordered += [e for e in pages[page] if not e[1]]
        for offer, _ in ordered:
            order += 1
            offer.catalog_order = order


def offer_from_api(data: dict, catalog: Catalog) -> Offer | None:
    pricing = data.get("pricing") or {}
    price = pricing.get("price")
    if price is None:
        return None
    amount, unit = parse_quantity(data.get("quantity"))
    images = data.get("images") or {}
    branding = data.get("branding") or {}
    offer = Offer(
        id=str(data["id"]),
        catalog_id=catalog.id,
        dealer=_first(branding.get("name"), catalog.dealer),
        heading=(data.get("heading") or "").strip(),
        description=(data.get("description") or "").strip(),
        price=float(price),
        pre_price=float(pricing["pre_price"]) if pricing.get("pre_price") else None,
        currency=pricing.get("currency") or "DKK",
        amount=amount,
        unit=unit,
        run_from=parse_datetime(data.get("run_from")) or catalog.run_from,
        run_till=parse_datetime(data.get("run_till")) or catalog.run_till,
        image_url=_first(images.get("view"), images.get("zoom"), images.get("thumb")),
        catalog_label=catalog.label,
        catalog_page=data.get("catalog_page") or None,
    )
    offer.enrich_from_text()
    return offer


class TjekSource:
    name = "tjek"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = API_BASE,
        timeout: float = 20.0,
        pause: float = 0.2,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.pause = pause

    # -- HTTP -----------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}/{path.lstrip('/')}?{query}"
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        request = urllib.request.Request(url, headers=headers)
        delay = 1.0
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise SourceError(f"Tjek API svarede {exc.code} for {url}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise SourceError(f"Kunne ikke kontakte Tjek API ({url}): {exc}") from exc
        raise SourceError(f"Kunne ikke hente {url}")

    def _paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict]:
        offset = 0
        while True:
            page = self._get(path, {**params, "limit": PAGE_SIZE, "offset": offset})
            if not isinstance(page, list):
                raise SourceError(f"Uventet svar fra Tjek API ({path}): {str(page)[:200]}")
            yield from page
            if len(page) < PAGE_SIZE:
                return
            offset += PAGE_SIZE
            time.sleep(self.pause)

    # -- OfferSource ----------------------------------------------------
    def list_catalogs(self, latitude: float, longitude: float, radius_km: float) -> list[Catalog]:
        params = {
            "r_lat": latitude,
            "r_lng": longitude,
            "r_radius": int(radius_km * 1000),
            "order_by": "-publication_date",
        }
        return [catalog_from_api(item) for item in self._paginate("catalogs", params)]

    def list_stores(self, dealer_id: str) -> list[dict]:
        """Kædens butikker i hele landet med adresse og koordinater."""
        return [
            {
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
                "zip_code": str(item.get("zip_code") or "").strip(),
                "city": str(item.get("city") or "").strip(),
            }
            for item in self._paginate("stores", {"dealer_ids": dealer_id})
            if item.get("latitude") is not None and item.get("longitude") is not None
        ]

    def list_offers(self, catalog: Catalog) -> list[Offer]:
        return offers_in_paper_order(self._paginate("offers", {"catalog_id": catalog.id}), catalog)

    def list_pages(self, catalog: Catalog) -> list[str]:
        """Billeder af avisens sider i rækkefølge."""
        pages = self._get(f"catalogs/{urllib.parse.quote(catalog.id)}/pages", {})
        if not isinstance(pages, list):
            raise SourceError(f"Uventet svar fra Tjek API (sider): {str(pages)[:200]}")
        return [_first(p.get("view"), p.get("zoom"), p.get("thumb")) or "" for p in pages if isinstance(p, dict)]


def offers_in_paper_order(items, catalog: Catalog) -> list[Offer]:
    offers = []
    placed = []
    for item in items:
        offer = offer_from_api(item, catalog)
        if offer is not None:
            offers.append(offer)
            images = item.get("images") or {}
            placed.append((offer, offer.catalog_page, image_box(_first(images.get("view"), images.get("thumb")))))
    paper_order(placed)
    return offers
