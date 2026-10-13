"""Datamodeller for tilbudsaviser og tilbud."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# Enhed -> (SI-enhed, faktor). Bruges når kilden ikke selv leverer SI-omregning.
_UNITS: dict[str, tuple[str, float]] = {
    "mg": ("kg", 0.000001),
    "g": ("kg", 0.001),
    "gr": ("kg", 0.001),
    "gram": ("kg", 0.001),
    "kilo": ("kg", 1.0),
    "kg": ("kg", 1.0),
    "ml": ("l", 0.001),
    "cl": ("l", 0.01),
    "dl": ("l", 0.1),
    "l": ("l", 1.0),
    "ltr": ("l", 1.0),
    "liter": ("l", 1.0),
    "stk": ("stk", 1.0),
    "pcs": ("stk", 1.0),
    "piece": ("stk", 1.0),
    "pieces": ("stk", 1.0),
}

_QUANTITY_RE = re.compile(
    r"(?:(?P<pieces>\d+)\s*[x×]\s*)?"
    r"(?P<size>\d+(?:[.,]\d+)?)(?:\s*-\s*\d+(?:[.,]\d+)?)?\s*"
    r"(?P<unit>kilo|kg|mg|gram|gr|g|ml|cl|dl|ltr|liter|l|stk)\b",
    re.IGNORECASE,
)


def normalize_unit(unit: str) -> tuple[str, float] | None:
    """Returnerer (SI-enhed, faktor) for en enhed som 'g' eller 'cl'."""
    return _UNITS.get(unit.strip().lower().rstrip("."))


def parse_quantity(text: str) -> tuple[float, str] | None:
    """Finder mængde i fritekst, fx '500 g', '6 x 33 cl' eller '1,5 kg'.

    Returnerer (mængde i SI-enhed, SI-enhed) eller None.
    """
    text = text or ""
    match = next(
        (
            m
            for m in _QUANTITY_RE.finditer(text)
            # "Max 3 stk. pr. kunde" er en begrænsning, ikke en mængde
            if not re.search(r"\b(max|maks)\.?\s*$", text[: m.start()], re.IGNORECASE)
        ),
        None,
    )
    if not match:
        return None
    unit = normalize_unit(match["unit"])
    if unit is None:
        return None
    si_unit, factor = unit
    size = float(match["size"].replace(",", "."))
    pieces = int(match["pieces"]) if match["pieces"] else 1
    amount = size * factor * pieces
    if amount <= 0:
        return None
    return amount, si_unit


@dataclass
class Catalog:
    """En tilbudsavis fra en butikskæde."""

    id: str
    dealer: str
    label: str
    run_from: datetime | None
    run_till: datetime | None
    offer_count: int | None = None
    url: str | None = None


@dataclass
class Offer:
    """Et enkelt tilbud fra en tilbudsavis."""

    id: str
    catalog_id: str
    dealer: str
    heading: str
    price: float
    description: str = ""
    pre_price: float | None = None
    currency: str = "DKK"
    amount: float | None = None  # Mængde i SI-enhed (kg, l eller stk)
    unit: str | None = None  # "kg", "l" eller "stk"
    run_from: datetime | None = None
    run_till: datetime | None = None
    image_url: str | None = None
    category: str | None = None
    # Udfyldes af scoringen
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.amount is None:
            parsed = parse_quantity(f"{self.heading} {self.description}")
            if parsed:
                self.amount, self.unit = parsed

    @property
    def unit_price(self) -> float | None:
        """Pris pr. kg, liter eller stk."""
        if self.amount and self.amount > 0 and self.unit:
            return self.price / self.amount
        return None

    @property
    def discount_pct(self) -> float | None:
        """Rabat i procent ift. førpris (0-100), hvis førpris kendes."""
        if self.pre_price and self.pre_price > self.price > 0:
            return (self.pre_price - self.price) / self.pre_price * 100
        return None

    @property
    def savings(self) -> float | None:
        """Besparelse i kroner ift. førpris."""
        if self.pre_price and self.pre_price > self.price:
            return self.pre_price - self.price
        return None

    @property
    def text(self) -> str:
        return f"{self.heading} {self.description}".strip()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "catalog_id": self.catalog_id,
            "dealer": self.dealer,
            "heading": self.heading,
            "description": self.description,
            "price": self.price,
            "pre_price": self.pre_price,
            "currency": self.currency,
            "amount": self.amount,
            "unit": self.unit,
            "unit_price": round(self.unit_price, 2) if self.unit_price else None,
            "discount_pct": round(self.discount_pct, 1) if self.discount_pct else None,
            "category": self.category,
            "run_from": self.run_from.isoformat() if self.run_from else None,
            "run_till": self.run_till.isoformat() if self.run_till else None,
            "image_url": self.image_url,
            "score": round(self.score, 1),
            "reasons": self.reasons,
        }
