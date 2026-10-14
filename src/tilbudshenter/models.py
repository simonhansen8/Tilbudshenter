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


# Et beløb som "79,90", "1.999,-", "219,-" eller "25"
_AMOUNT = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}|-))?"
_STATED_UNIT_PRICE_RE = re.compile(
    rf"\bpr\.?\s*(kg|kilo|liter|ltr|l)\.?\s*(?:maks\.?|max\.?)?\s*(\d{{1,3}}(?:\.\d{{3}})*,\d{{2}})",
    re.IGNORECASE,
)
_NORMAL_PRICE_RE = re.compile(rf"\b(?:normalpris|normal pris|før)\.?\s*(op til\s*)?{_AMOUNT}", re.IGNORECASE)
# Intervaller som "Spar 13-35 %" springes over
_SAVE_RE = re.compile(rf"\bspar\s*(op til\s*)?{_AMOUNT}(?![\d.,]|\s*-\s*\d)\s*(%)?", re.IGNORECASE)


# Tilbud der kræver medlemskab eller kædens app, fx "Med Lidl Plus",
# "Gælder kun med føtex plus appen", "+ PRIS 10.-" (Netto+) og Coops
# "Medlemspris" / "Pris ikke-medlem 26,00".
_MEMBER_RE = re.compile(
    r"lidl plus|medlemspris|medlems-?\s?rabat|ikke-medlem|uden medlemskab|medlems\s*køb"
    r"|plus[- ]?pris|(?:^|\s)\+\s?pris|plus[- ]?app|netto\+|kun med [\w\s+]{0,20}app",
    re.IGNORECASE,
)


def member_requirement(text: str) -> str | None:
    """Hvad tilbuddet kræver: "Lidl Plus", "Kræver app", "Medlemspris" eller None."""
    match = _MEMBER_RE.search(text or "")
    if not match:
        return None
    found = match[0].casefold()
    if "lidl" in found:
        return "Lidl Plus"
    if "medlem" in found:
        return "Medlemspris"
    return "Kræver app"


def _to_float(whole: str, fraction: str | None) -> float:
    value = float(whole.replace(".", ""))
    if fraction and fraction != "-":
        value += int(fraction) / 100
    return value


def parse_stated_unit_price(text: str) -> tuple[float, str] | None:
    """Finder butikkens egen enhedspris, fx 'Pr. kg 79,90' -> (79.9, 'kg')."""
    match = _STATED_UNIT_PRICE_RE.search(text or "")
    if not match:
        return None
    unit = normalize_unit(match[1])
    whole, _, fraction = match[2].partition(",")
    price = _to_float(whole, fraction)
    return (price, unit[0]) if unit and price > 0 else None


def parse_reference_price(text: str, price: float) -> float | None:
    """Udleder normalprisen fra tekst som 'Normalpris 219,-', 'Spar 43,80'
    eller 'Spar 25 %'. Tvetydige angivelser ("op til", flere forskellige
    normalpriser, intervaller) ignoreres."""
    text = text or ""
    candidates = {
        _to_float(m[2], m[3]) for m in _NORMAL_PRICE_RE.finditer(text) if not m[1]
    }
    if len(candidates) == 1:
        reference = candidates.pop()
    else:
        saves = [m for m in _SAVE_RE.finditer(text) if not m[1]]
        if len(saves) != 1 or len(candidates) > 1:
            return None
        save = _to_float(saves[0][2], saves[0][3])
        if saves[0][4]:  # procent
            if not 0 < save < 100:
                return None
            reference = price / (1 - save / 100)
        else:
            reference = price + save
    if price < reference < price * 10:
        return round(reference, 2)
    return None


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
    catalog_label: str = ""
    # Udfyldes af scoringen
    score: float = 0.0
    known_discount: float | None = None  # Rabat i % fra førpris, prishistorik eller andre butikker
    discount_basis: str | None = None  # "foerpris", "historik" eller "butikker"
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.amount is None:
            parsed = parse_quantity(f"{self.heading} {self.description}")
            if parsed:
                self.amount, self.unit = parsed

    def enrich_from_text(self) -> None:
        """Supplerer data ud fra beskrivelsen.

        Mange aviser angiver ikke førpris som et felt, men skriver fx
        "Normalpris 219,-" eller "Spar 25 %" i teksten. Butikkens egen
        enhedspris ("Pr. kg 79,90") er mere pålidelig end en udregnet.
        """
        if self.pre_price is None:
            self.pre_price = parse_reference_price(self.description, self.price)
        stated = parse_stated_unit_price(self.description)
        if stated:
            unit_price, unit = stated
            self.amount, self.unit = self.price / unit_price, unit

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

    @property
    def member(self) -> str | None:
        """Kræver tilbuddet medlemskab eller app? Se ``member_requirement``."""
        return member_requirement(self.text)

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
            "known_discount": round(self.known_discount, 1) if self.known_discount is not None else None,
            "discount_basis": self.discount_basis,
            "member": self.member,
            "catalog_label": self.catalog_label,
            "reasons": self.reasons,
        }
