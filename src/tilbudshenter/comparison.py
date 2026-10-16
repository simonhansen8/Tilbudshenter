"""Sammenligning af samme vare på tværs af butikker.

Mange kæder (fx Netto, REMA 1000 og 365discount) oplyser næsten aldrig en
normalpris, så rabatten kan ikke beregnes. I stedet sammenlignes prisen pr.
kg eller liter med de andre butikkers tilbud på samme slags vare i de
aktuelle aviser: Er hakket oksekød 25 % billigere i Netto end i de andre
butikker, er det et godt tilbud.

Varerne genkendes ud fra en fast liste af almindelige basisvarer. Et
tilbud på flere forskellige varer ("Hakket okse- eller grisekød") eller en
færdigret sammenlignes ikke, da prisen pr. kg så ikke kan tolkes sikkert.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass

from .models import PAPER_TWINS, Offer

# Varetype -> (navn, mønstre, ekstra udelukkelser). Et mønster er en liste
# af ord, der alle skal stå i varenavnet. Et ord matcher også sammensatte
# ord, der begynder eller slutter med det ("kyllingebryst" matcher
# "kyllingebrystfilet"), medmindre det slutter med mellemrum ("smør ").
PRODUCT_GROUPS: dict[str, tuple[str, list[list[str]], list[str]]] = {
    "hakket_okse": ("hakket oksekød", [["hakket", "okse"]], ["gris", "kylling", "grønt", "kalv"]),
    "hakket_gris": ("hakket grisekød", [["hakket", "grisekød"], ["hakket", "gris "]], ["kalv", "okse"]),
    "hakket_gris_kalv": ("hakket grise- og kalvekød", [["hakket", "gris", "kalv"]], ["okse"]),
    "hakket_kylling": ("hakket kyllingekød", [["hakket", "kylling"]], []),
    "hakket_kalkun": ("hakket kalkunkød", [["hakket", "kalkun"]], []),
    "kyllingebryst": ("kyllingebryst", [["kyllingebryst"], ["kyllingefilet"]], ["lage"]),
    "bacon": ("bacon", [["bacon"]], ["leverpostej", "kalkun", "pølse", "ost"]),
    "medister": ("medister", [["medister"]], []),
    "leverpostej": ("leverpostej", [["leverpostej"]], []),
    "flaeskesteg": ("flæskesteg", [["flæskesteg"]], []),
    "moerbrad": ("mørbrad af gris", [["mørbrad"]], ["bøf", "okse", "kalv", "hjort", "lam"]),
    "laksefilet": ("laksefilet", [["laksefilet"], ["laks", "filet"], ["laksestykke"], ["lakseportion"]],
                   ["røget", "gravad", "rogn"]),
    "torsk": ("torsk", [["torsk"]], ["fars", "rogn", "lever"]),
    "smoer": ("smør", [["smør "]], []),
    "letmaelk": ("letmælk", [["letmælk"]], []),
    "minimaelk": ("minimælk", [["minimælk"]], []),
    "soedmaelk": ("sødmælk", [["sødmælk"]], []),
    "skyr": ("skyr", [["skyr"]], []),
    "aeg": ("æg", [["æg "], ["skrabeæg"], ["frilandsæg"], ["buræg"]], ["påske", "chokolade"]),
    "bananer": ("bananer", [["bananer "], ["banan "]], []),
    "aebler": ("æbler", [["æbler "], ["æble "]], []),
    "paerer": ("pærer", [["pærer "], ["pære "]], []),
    "kartofler": ("kartofler", [["kartofler"]], ["mos", "båd", "røsti", "fritter", "fløde"]),
    "guleroedder": ("gulerødder", [["gulerød"]], []),
    "loeg": ("løg", [["løg "]], []),
    "tomater": ("tomater", [["tomater"]], ["flåede", "hakkede", "soltørrede", "passata", "cherry", "snack"]),
    "agurk": ("agurk", [["agurk"]], []),
    "peberfrugt": ("peberfrugt", [["peberfrugt"]], []),
    "broccoli": ("broccoli", [["broccoli"]], ["blomkål"]),
    "kaffe": ("kaffe", [["kaffe"]], ["kapsler", "pads", "instant", "nescafé", "nescafe", "bønner", "filter", "fløde"]),
    "havregryn": ("havregryn", [["havregryn"]], []),
    "spaghetti": ("spaghetti", [["spaghetti"]], ["græskar"]),
    "ris": ("ris", [["ris "], ["jasminris"], ["basmatiris"]], ["grød", "kiks", "papir"]),
    "hvedemel": ("hvedemel", [["hvedemel"]], []),
    "sukker": ("sukker", [["sukker "]], []),
    "olivenolie": ("olivenolie", [["olivenolie"]], []),
    "rugbroed": ("rugbrød", [["rugbrød"]], []),
    "toastbroed": ("toastbrød", [["toastbrød"]], []),
}

# Varer der sælges og kan sammenlignes pr. stk. Alle andre sammenlignes
# kun pr. kg eller liter, da en stykpris afhænger af pakningens størrelse.
PER_PIECE_GROUPS = {"aeg", "agurk", "peberfrugt", "bananer"}

# Ord der betyder, at varen ikke kan sammenlignes med almindelige basisvarer
_EXCLUDE_ALWAYS = [
    "økologisk", "øko", "færdigret", "gratin", "pålæg", "suppe", "sauce",
    "salat", "spyd", "kebab", "marineret", "dressing", "chips", "juice",
    "most", "snack", "grød", "fyld",
]

# En billigere pris end dette i forhold til de andre butikker er næsten
# altid en fejl i mængden (fx en multipakke), ikke et tilbud.
MAX_DISCOUNT_PCT = 65.0


@dataclass
class Comparison:
    group: str  # varetypens navn, fx "hakket oksekød"
    reference: float  # de andre butikkers typiske pris pr. enhed
    other_stores: int  # antal andre butikker med samme vare


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


def _has_word(tokens: list[str], word: str) -> bool:
    whole = word.endswith(" ")
    word = word.strip().casefold()
    return any(t == word or (not whole and (t.startswith(word) or t.endswith(word))) for t in tokens)


def _group_of(text: str) -> str | None:
    tokens = _tokens(text)
    if any(_has_word(tokens, w) for w in _EXCLUDE_ALWAYS):
        return None
    for key, (_, patterns, exclude) in PRODUCT_GROUPS.items():
        if any(_has_word(tokens, w) for w in exclude):
            continue
        if any(all(_has_word(tokens, w) for w in pattern) for pattern in patterns):
            return key
    return None


def product_group(heading: str) -> str | None:
    """Finder varetypen for et varenavn, fx "Netto hakket oksekød 8-12%".

    Nævner navnet flere varer ("Bacon eller hamburgerryg"), skal de alle
    være af samme type. Varianter som "-inderfilet" regnes med til den
    første vare.
    """
    # Kun "eller" og komma adskiller varer; "grise- og kalvekød" er én vare
    parts = [p.strip() for p in re.split(r",|\beller\b", heading, flags=re.IGNORECASE)]
    parts = [p for p in parts if p and not p.startswith("-")]
    groups = {_group_of(p) for p in parts}
    return groups.pop() if len(groups) == 1 else None


def _store_key(dealer: str) -> str:
    # En kæde uden egen avis har samme priser som kæden, hvis avis den
    # bruger, og må ikke tælle som en anden butik
    dealer = PAPER_TWINS.get(dealer, dealer)
    return re.sub(r"[^\w]+", "", dealer.casefold())


def compare_across_stores(offers: list[Offer]) -> dict[str, Comparison]:
    """Sammenligner enhedsprisen for hvert tilbud med de andre butikkers.

    Returnerer {tilbuds-id: Comparison} for tilbud, der er billigere pr. kg
    eller liter end medianen af de andre butikkers billigste tilbud på
    samme varetype.
    """
    # (varetype, enhed) -> butik -> laveste enhedspris
    best: dict[tuple[str, str], dict[str, float]] = {}
    grouped: list[tuple[Offer, tuple[str, str]]] = []
    for offer in offers:
        unit_price = offer.unit_price
        if not unit_price or offer.unit not in ("kg", "l", "stk"):
            continue
        group = product_group(offer.heading)
        if group is None or (offer.unit == "stk" and group not in PER_PIECE_GROUPS):
            continue
        key = (group, offer.unit)
        store = _store_key(offer.dealer)
        prices = best.setdefault(key, {})
        prices[store] = min(prices.get(store, unit_price), unit_price)
        grouped.append((offer, key))

    result: dict[str, Comparison] = {}
    for offer, key in grouped:
        own = _store_key(offer.dealer)
        others = [price for store, price in best[key].items() if store != own]
        if not others:
            continue
        reference = statistics.median(others)
        discount = (1 - offer.unit_price / reference) * 100
        if 0 < discount <= MAX_DISCOUNT_PCT:
            result[offer.id] = Comparison(PRODUCT_GROUPS[key[0]][0], reference, len(others))
    return result
