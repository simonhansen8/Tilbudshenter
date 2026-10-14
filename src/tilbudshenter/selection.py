"""Filtrering og rangering af tilbud efter brugerens valg."""

from __future__ import annotations

import re
from collections import Counter

from .categories import Categorizer
from .comparison import Comparison, compare_across_stores
from .config import Config
from .models import Offer
from .storage import product_key


def _norm_store(name: str) -> str:
    return re.sub(r"[^\w]+", "", name.casefold())


def store_selected(dealer: str, cfg: Config) -> bool:
    """Er butikken valgt? Navne matches uden hensyn til store/små bogstaver
    og mellemrum, og et navn matcher også længere navne ("365" matcher
    "365discount")."""
    dealer_n = _norm_store(dealer)

    def matches(names: list[str]) -> bool:
        return any(dealer_n.startswith(_norm_store(n)) for n in names if _norm_store(n))

    if cfg.exclude_stores and matches(cfg.exclude_stores):
        return False
    return not cfg.stores or matches(cfg.stores)


def catalog_selected(label: str, cfg: Config, dealer: str = "") -> bool:
    """Er avisen valgt? Matches på en del af avisens navn. "føtex: Uge 42"
    gælder kun avisen "Uge 42" fra føtex, ikke de andre kæders "Uge 42"."""
    if _catalog_matches(dealer, label, cfg.exclude_catalogs):
        return False
    return not cfg.catalogs or _catalog_matches(dealer, label, cfg.catalogs)


def _catalog_matches(dealer: str, label: str, words: list[str]) -> bool:
    lowered = label.casefold()
    for word in words:
        chain, sep, part = word.partition(":")
        if sep and _norm_store(chain) and part.strip():
            if _norm_store(dealer).startswith(_norm_store(chain)) and part.strip().casefold() in lowered:
                return True
        elif word.strip() and word.casefold() in lowered:
            return True
    return False


def _contains_any(text: str, words: list[str]) -> str | None:
    lowered = text.casefold()
    return next((w for w in words if w.strip() and w.casefold() in lowered), None)


# Ekstra point til et tilbud med den laveste pris i flere uger
LOWEST_PRICE_BONUS = 5.0


def score_offer(
    offer: Offer,
    cfg: Config,
    typical_prices: dict[tuple[str, str], float] | None = None,
    comparisons: dict[str, Comparison] | None = None,
    lows: dict[str, int] | None = None,
) -> float | None:
    """Beregner en score (højere = bedre) og udfylder ``offer.reasons``.

    Grundscoren er rabatten i procent - fra førprisen. Mangler den, bruges
    varens typiske enhedspris i tidligere aviser, og ellers de andre
    butikkers pris pr. kg/liter på samme varetype i de aktuelle aviser.
    Favoritter får en bonus, og store besparelser i kroner giver et lille
    ekstra skub. Returnerer den kendte rabat i procent (eller None).
    """
    reasons: list[str] = []
    discount = offer.discount_pct
    basis = "foerpris" if discount is not None else None
    if discount is not None:
        reasons.append(f"-{discount:.0f}% (spar {offer.savings:.2f} kr)".replace(".", ","))
    elif typical_prices and offer.unit_price and offer.unit:
        typical = typical_prices.get((product_key(offer.heading), offer.unit))
        if typical and typical > offer.unit_price:
            discount = (1 - offer.unit_price / typical) * 100
            basis = "historik"
            reasons.append(f"{discount:.0f}% under normal enhedspris".replace(".", ","))
    if discount is None and comparisons and (comparison := comparisons.get(offer.id)):
        discount = (1 - offer.unit_price / comparison.reference) * 100
        basis = "butikker"
        others = "1 anden butik" if comparison.other_stores == 1 else f"{comparison.other_stores} andre butikker"
        reasons.append(
            f"{discount:.0f}% billigere end {comparison.group} i {others} "
            f"(typisk {comparison.reference:.2f} kr/{offer.unit})".replace(".", ",")
        )

    score = discount or 0.0
    offer.lowest_weeks = (lows or {}).get(offer.id)
    if offer.lowest_weeks:
        score += LOWEST_PRICE_BONUS
        reasons.append(f"laveste pris i {offer.lowest_weeks} uger")
    if offer.savings:
        score += min(offer.savings, 100) / 20
    if favorite := _contains_any(offer.text, cfg.favorites):
        score += cfg.favorite_bonus
        reasons.append(f"favorit ({favorite})")

    offer.score = score
    offer.known_discount = discount
    offer.discount_basis = basis
    offer.reasons = reasons
    return discount


def select_offers(
    offers: list[Offer],
    cfg: Config,
    categorizer: Categorizer,
    typical_prices: dict[tuple[str, str], float] | None = None,
    limit: int | None = None,
    lows: dict[str, int] | None = None,
) -> list[Offer]:
    """Filtrerer tilbud efter butik, kategori og filtre og sorterer de
    bedste først."""
    candidates = [
        o for o in offers
        if store_selected(o.dealer, cfg) and catalog_selected(o.catalog_label, cfg, o.dealer)
    ]
    # Sammenlign med de valgte butikker, uanset kategori- og prisfiltre
    comparisons = compare_across_stores(candidates)
    selected: list[Offer] = []
    for offer in candidates:
        offer.category = categorizer.categorize(offer.heading, offer.description)
        if cfg.categories and offer.category not in cfg.categories:
            continue
        if offer.category in cfg.exclude_categories:
            continue
        if cfg.max_price is not None and offer.price > cfg.max_price:
            continue
        if cfg.include_keywords and not _contains_any(offer.text, cfg.include_keywords):
            continue
        if _contains_any(offer.text, cfg.exclude_keywords):
            continue

        discount = score_offer(offer, cfg, typical_prices, comparisons, lows)
        if not _contains_any(offer.text, cfg.favorites):
            if discount is None and cfg.only_known_discount:
                continue
            if discount is not None and discount < cfg.min_discount_pct:
                continue
        selected.append(offer)

    # Bedste score først. Tilbud uden kendt rabat (score 0) kommer sidst,
    # grupperet efter kategori og med laveste enhedspris først.
    selected.sort(key=lambda o: (
        -o.score,
        categorizer.display_name(o.category) if o.score == 0 else "",
        o.unit_price or float("inf"),
        o.price,
    ))
    selected = _dedupe(selected)

    if cfg.per_category > 0:
        counts: Counter[str] = Counter()
        limited = []
        for offer in selected:
            if counts[offer.category or ""] < cfg.per_category:
                counts[offer.category or ""] += 1
                limited.append(offer)
        selected = limited

    limit = cfg.top_n if limit is None else limit
    return selected[:limit] if limit and limit > 0 else selected


def _dedupe(offers: list[Offer]) -> list[Offer]:
    """Fjerner samme tilbud fra samme butik (fx hvis det står i to aviser)."""
    seen: set[tuple] = set()
    result = []
    for offer in offers:
        key = (_norm_store(offer.dealer), product_key(offer.heading), offer.price)
        if key not in seen:
            seen.add(key)
            result.append(offer)
    return result
