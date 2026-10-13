"""Scanning: find nye tilbudsaviser og hent deres tilbud."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .categories import Categorizer
from .config import Config
from .models import Catalog
from .selection import catalog_selected, store_selected
from .sources.base import OfferSource, SourceError
from .storage import Storage

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    new_catalogs: list[Catalog] = field(default_factory=list)
    known_catalogs: list[Catalog] = field(default_factory=list)
    failed: list[tuple[Catalog, str]] = field(default_factory=list)
    offers_fetched: int = 0

    @property
    def found_new(self) -> bool:
        return bool(self.new_catalogs)


def scan(
    cfg: Config,
    source: OfferSource,
    storage: Storage,
    categorizer: Categorizer,
    force: bool = False,
    now: datetime | None = None,
) -> ScanResult:
    """Henter aviser for de valgte butikker. Aviser der allerede er scannet,
    springes over (medmindre ``force``)."""
    now = now or datetime.now(timezone.utc)
    result = ScanResult()
    catalogs = source.list_catalogs(cfg.latitude, cfg.longitude, cfg.radius_km)
    for catalog in catalogs:
        if not store_selected(catalog.dealer, cfg) or not catalog_selected(catalog.label, cfg):
            continue
        if catalog.run_till and catalog.run_till < now:
            continue
        if not force and storage.is_scanned(catalog.id):
            result.known_catalogs.append(catalog)
            continue
        log.info("Henter tilbud fra %s - %s", catalog.dealer, catalog.label)
        try:
            offers = source.list_offers(catalog)
        except SourceError as exc:
            log.warning("Kunne ikke hente %s: %s", catalog.label, exc)
            result.failed.append((catalog, str(exc)))
            continue
        for offer in offers:
            offer.category = categorizer.categorize(offer.heading, offer.description)
        storage.save_catalog(catalog, source.name, scanned=True)
        storage.save_offers(offers)
        result.new_catalogs.append(catalog)
        result.offers_fetched += len(offers)
    return result
