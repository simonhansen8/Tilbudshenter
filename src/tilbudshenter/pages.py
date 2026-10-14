"""Statisk udgave af appen til GitHub Pages.

En GitHub Actions-workflow henter aviserne (det kan browseren ikke selv,
da Tjek ikke tillader kald fra andre hjemmesider) og bygger en mappe med
``index.html`` og ``data.json``. Siden læser tilbuddene fra ``data.json``,
og brugerens indstillinger og indkøbsliste gemmes i browseren.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .categories import UNCATEGORIZED, Categorizer, merge_categories
from .cli import best_offers
from .config import NEW_STORES, Config, example_config
from .models import Catalog, Offer
from .selection import store_selected
from .sources.base import SourceError
from .storage import Storage
from .webapp import offer_payload, settings_from_config

log = logging.getLogger(__name__)

# Butikker der hentes til siden. Brugeren vælger blandt dem i browseren;
# standardvalget er det samme som i en ny konfiguration.
SITE_STORES = [
    "Netto", "REMA 1000", "Lidl", "føtex", "Bilka", "365discount", *NEW_STORES,
    "Coop", "Min Købmand", "LET-KØB", "ABC Lavpris", "Købmandsgården",
]

# Steder aviserne søges fra, så kæder der kun findes i en del af landet
# også kommer med. Brugeren vælger selv sin placering på siden.
SCAN_POINTS = [
    (55.676, 12.568),  # København
    (56.157, 10.211),  # Aarhus
    (57.048, 9.919),   # Aalborg
    (57.460, 9.980),   # Hjørring
    (56.360, 8.620),   # Holstebro
    (55.477, 8.459),   # Esbjerg
    (55.396, 10.388),  # Odense
    (54.910, 9.790),   # Sønderborg
    (54.770, 11.870),  # Nykøbing F
    (55.101, 14.707),  # Rønne
]
SCAN_RADIUS_KM = 60

# Kæder hvis aviser gælder i hele landet uanset butikker (Coop er
# fællesnavnet for Coops kæder og har næsten ingen egne butikker)
NATIONWIDE = {"Coop"}


class CountrySource:
    """Søger aviser fra flere steder i landet og husker kædernes id'er,
    så deres butikker kan hentes bagefter."""

    def __init__(self, source) -> None:
        self.source = source
        self.name = source.name
        self.dealer_ids: dict[str, str] = {}

    def list_catalogs(self, latitude: float, longitude: float, radius_km: float) -> list[Catalog]:
        catalogs: dict[str, Catalog] = {}
        for lat, lng in SCAN_POINTS:
            for catalog in self.source.list_catalogs(lat, lng, SCAN_RADIUS_KM):
                catalogs.setdefault(catalog.id, catalog)
                if catalog.dealer_id:
                    self.dealer_ids.setdefault(catalog.dealer, catalog.dealer_id)
        return list(catalogs.values())

    def list_offers(self, catalog: Catalog) -> list[Offer]:
        return self.source.list_offers(catalog)

    def store_locations(self, cfg: Config) -> dict[str, list[dict]]:
        """Butikkerne for de kæder, siden viser. En kæde, hvis butikker
        ikke kan hentes, udelades (siden viser den så uanset placering)."""
        result = {}
        for dealer, dealer_id in sorted(self.dealer_ids.items()):
            if dealer in NATIONWIDE or not store_selected(dealer, cfg):
                continue
            try:
                result[dealer] = self.source.list_stores(dealer_id)
            except SourceError as exc:
                log.warning("Kunne ikke hente butikker for %s: %s", dealer, exc)
        return result


def places_from_stores(stores: dict[str, list[dict]]) -> list[list]:
    """Postnumre med by og et midtpunkt, ud fra butikkernes adresser.
    Bruges til at søge en placering frem på siden."""
    by_zip: dict[str, dict] = {}
    for items in stores.values():
        for s in items:
            if not (s["zip_code"].isdigit() and len(s["zip_code"]) == 4):
                continue
            entry = by_zip.setdefault(s["zip_code"], {"cities": {}, "lat": [], "lng": []})
            entry["cities"][s["city"]] = entry["cities"].get(s["city"], 0) + 1
            entry["lat"].append(s["latitude"])
            entry["lng"].append(s["longitude"])
    return [
        [zip_code, max(e["cities"], key=e["cities"].get),
         round(statistics.median(e["lat"]), 4), round(statistics.median(e["lng"]), 4)]
        for zip_code, e in sorted(by_zip.items())
    ]


STATIC_MARKER = "<script>window.TILBUDSHENTER_STATIC = true;</script>"


def site_config() -> Config:
    """Konfigurationen workflowen henter med: alle butikker siden tilbyder,
    og ingen af brugerens filtre (de anvendes i browseren)."""
    base = example_config()
    return replace(base, stores=list(SITE_STORES), categories=[])


def site_data(cfg: Config, now: datetime | None = None, stores: dict[str, list[dict]] | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    categorizer = Categorizer(merge_categories(cfg.custom_categories))
    wide = replace(
        cfg, categories=[], exclude_categories=[], min_discount_pct=0.0, only_known_discount=False,
        max_price=None, include_keywords=[], exclude_keywords=[], favorites=[], top_n=0, per_category=0,
    )
    with Storage(cfg.database) as storage:
        offers = best_offers(wide, storage, categorizer, now, limit=0)
        catalogs = storage.catalogs(active_at=now)
        last = storage.last_scan()

    by_store: dict[str, list] = {}
    for c in catalogs:
        by_store.setdefault(c.dealer, []).append(c)
    stores = stores or {}
    defaults = settings_from_config(example_config())
    # Ingen placering, før brugeren vælger en; så vises alle butikker
    defaults.update(latitude=None, longitude=None, radius_km=10.0, place="")
    return {
        "generated": now.isoformat(),
        "last_scan": last.isoformat() if last else None,
        "catalog_count": len(catalogs),
        "favorite_bonus": cfg.favorite_bonus,
        "default_settings": defaults,
        "categories": [
            {"key": key, "name": spec["navn"]} for key, spec in categorizer.categories.items()
        ] + [{"key": UNCATEGORIZED, "name": categorizer.display_name(UNCATEGORIZED)}],
        "stores": [
            {
                "name": name,
                "catalogs": [
                    {
                        "label": c.label.strip() or "(uden navn)",
                        "period": f"{c.run_from:%d/%m}-{c.run_till:%d/%m}" if c.run_from and c.run_till else "",
                    }
                    for c in sorted(items, key=lambda c: c.label.casefold())
                ],
                # [breddegrad, længdegrad] for hver butik; mangler, hvis ukendt
                **({"locations": [[round(s["latitude"], 4), round(s["longitude"], 4)] for s in stores[name]]}
                   if name in stores else {}),
            }
            for name, items in sorted(by_store.items(), key=lambda kv: kv[0].casefold())
        ],
        "places": places_from_stores(stores),
        "offers": [offer_payload(o, categorizer) for o in offers],
    }


def static_html() -> str:
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    return html.replace("<script>\n", STATIC_MARKER + "\n<script>\n", 1)


def build_site(
    cfg: Config, out_dir: Path, now: datetime | None = None, stores: dict[str, list[dict]] | None = None,
) -> dict:
    """Skriver index.html og data.json i ``out_dir``. Returnerer dataene."""
    data = site_data(cfg, now, stores)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(static_html(), encoding="utf-8")
    (out_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return data
