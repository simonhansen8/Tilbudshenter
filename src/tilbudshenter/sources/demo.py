"""Kilde: indbyggede demodata.

Bruges til at prøve programmet uden netværksadgang (``--demo``) og i
testene. Data har samme format som Tjek's API, så de går gennem samme
fortolkning som rigtige data. Datoerne flyttes, så aviserne altid er
aktuelle.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from ..models import Catalog, Offer
from .tjek import catalog_from_api, offer_from_api


class DemoSource:
    name = "demo"

    def __init__(self, path: Path | None = None, now: datetime | None = None) -> None:
        if path is None:
            text = resources.files("tilbudshenter.data").joinpath("demo.json").read_text("utf-8")
        else:
            text = Path(path).read_text("utf-8")
        self._data = json.loads(text)
        now = now or datetime.now(timezone.utc)
        self._start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

    def _catalog(self, raw: dict) -> Catalog:
        catalog = catalog_from_api(raw)
        offset = timedelta(days=raw.get("start_offset_days", 0))
        catalog.run_from = self._start + offset
        catalog.run_till = catalog.run_from + timedelta(days=7)
        return catalog

    def list_catalogs(self, latitude: float, longitude: float, radius_km: float) -> list[Catalog]:
        return [self._catalog(raw) for raw in self._data["catalogs"]]

    def list_offers(self, catalog: Catalog) -> list[Offer]:
        for raw in self._data["catalogs"]:
            if str(raw["id"]) == catalog.id:
                offers = (offer_from_api(item, catalog) for item in raw.get("offers", []))
                return [o for o in offers if o is not None]
        return []
