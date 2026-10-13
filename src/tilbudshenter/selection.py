"""Filtrering og rangering af tilbud efter brugerens valg."""

from __future__ import annotations

import re
from collections import Counter

from .categories import Categorizer
from .config import Config
from .models import Offer
from .storage import product_key


def _norm_store(name: str) -> str:
    return re.sub(r"[^\w]+", "", name.casefold())


def store_selected(dealer: str, cfg: Config) -> bool:
    """Er butikken valgt? Navne matches uden hensyn til store/små bogstaver
    og mellemrum, og "Coop 365" matcher fx også "Coop 365discount"."""
    dealer_n = _norm_store(dealer)

    def matches(names: list[str]) -> bool:
        return any(dealer_n.startswith(_norm_store(n)) for n in names if _norm_store(n))

    if cfg.exclude_stores and matches(cfg.exclude_stores):
        return False
    return not cfg.stores or matches(cfg.stores)


def _contains_any(text: str, words: list[str]) -> str | None:
    lowered = text.casefold()
    return next((w for w in words if w.strip() and w.casefold() in lowered), None)


def score_offer(
    offer: Offer,
    cfg: Config,
    typical_prices: dict[tuple[str, str], float] | None = None,
) -> float | None:
    """Beregner en score (højere = bedre) og udfylder ``offer.reasons``.

    Grundscoren er rabatten i procent - fra førprisen, eller hvis den
    mangler, ift. varens typiske enhedspris i tidligere aviser. Favoritter
    får en bonus, og store besparelser i kroner giver et lille ekstra skub.
    Returnerer den kendte rabat i procent (eller None).
    """
    reasons: list[str] = []
    discount = offer.discount_pct
    if discount is not None:
        reasons.append(f"-{discount:.0f}% (spar {offer.savings:.2f} kr)".replace(".", ","))
    elif typical_prices and offer.unit_price and offer.unit:
        typical = typical_prices.get((product_key(offer.heading), offer.unit))
        if typical and typical > offer.unit_price:
            discount = (1 - offer.unit_price / typical) * 100
            reasons.append(f"{discount:.0f}% under normal enhedspris".replace(".", ","))

    score = discount or 0.0
    if offer.savings:
        score += min(offer.savings, 100) / 20
    if favorite := _contains_any(offer.text, cfg.favorites):
        score += cfg.favorite_bonus
        reasons.append(f"favorit ({favorite})")

    offer.score = score
    offer.reasons = reasons
    return discount


def select_offers(
    offers: list[Offer],
    cfg: Config,
    categorizer: Categorizer,
    typical_prices: dict[tuple[str, str], float] | None = None,
    limit: int | None = None,
) -> list[Offer]:
    """Filtrerer tilbud efter butik, kategori og filtre og sorterer de
    bedste først."""
    selected: list[Offer] = []
    for offer in offers:
        if not store_selected(offer.dealer, cfg):
            continue
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

        discount = score_offer(offer, cfg, typical_prices)
        if cfg.min_discount_pct > 0 and not _contains_any(offer.text, cfg.favorites):
            # Uden kendt rabat kan vi ikke vurdere tilbuddet - spring over.
            if discount is None or discount < cfg.min_discount_pct:
                continue
        selected.append(offer)

    selected.sort(key=lambda o: (-o.score, o.unit_price or float("inf"), o.price))
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
