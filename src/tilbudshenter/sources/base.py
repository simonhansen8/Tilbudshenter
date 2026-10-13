"""Fælles interface for datakilder.

En ny kilde (fx en anden avis-tjeneste eller en butiks egen hjemmeside)
skal blot implementere de to metoder herunder.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Catalog, Offer


class SourceError(RuntimeError):
    """Fejl ved hentning fra en datakilde."""


class OfferSource(Protocol):
    name: str

    def list_catalogs(self, latitude: float, longitude: float, radius_km: float) -> list[Catalog]:
        """Aktuelle og kommende tilbudsaviser i området."""
        ...

    def list_offers(self, catalog: Catalog) -> list[Offer]:
        """Alle tilbud i en given avis."""
        ...
