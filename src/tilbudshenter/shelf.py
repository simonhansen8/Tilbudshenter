"""Normalpriser på varer uden tilbud, hentet fra kædernes webshops.

Madplanen regner varer uden tilbud til basisprisen. I stedet for de
anslåede priser i ``mealplan.NORMAL_PRICES`` bruges den rigtige hyldepris,
når en webshop har varen: den billigste almindelige (ikke økologiske)
udgave pr. kg eller liter. Priserne hentes med hver opdatering og gemmes i
``normalpriser.json``; svarer webshoppen ikke, bruges de sidst hentede.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .comparison import _has_word, _tokens
from .mealplan import NORMAL_PRICES, department, ingredient_keys
from .sources.base import SourceError
from .sources.rema import ShelfPrice, fetch_shelf_prices

FILE_NAME = "normalpriser.json"
# Hentes igen, når priserne er ældre end dette
MAX_AGE = timedelta(hours=20)

# Webshoppens afdelinger, hver slags ingrediens findes i (madplanens
# afdeling -> webshoppens). Så er fx citronyoghurt ikke en citron, og
# drikkevarer, husholdning og færdigretter er aldrig råvarer.
DEPARTMENTS = {
    "koed": {"kød, fisk & fjerkræ", "køl", "frost"},
    "fisk": {"kød, fisk & fjerkræ", "køl", "frost"},
    "kolonial": {"kolonial"},
    "mejeri": {"mejeri", "ost m.v.", "køl"},
    "broed_og_bager": {"brød & bavinchi", "kolonial"},
    "frugt_og_groent": {"frugt & grønt"},
    "frost": {"frost"},
}
# Varenavne, der ikke er råvaren, selvom de nævner den
_NOT_RAW = ["postej", "katte", "hunde", "relish", "dip", "snack", "gum", "pålæg", "mesterpålæg", "dressing",
            "suppe", "drik", "smoothie", "is ", "grønt"]
# Webshoppens navne for varer, madplanen kender under et andet navn
_ALIASES = [
    (re.compile(r"^stegeflæsk\b", re.IGNORECASE), "stegeflaesk"),
    (re.compile(r"^(rød|gul|grøn|gul/orange) peber$", re.IGNORECASE), "peberfrugt"),
    (re.compile(r"^ungkvæg i tern\b", re.IGNORECASE), "okse_tern"),
]
# En rigtig hyldepris ligger inden for dette af den anslåede pris; ellers er
# varen næppe den samme (fx "smør" til 40 kr/kg eller frugtspaghetti)
MIN_RATIO, MAX_RATIO = 0.35, 2.5


def _organic(p: ShelfPrice) -> bool:
    return p.organic or bool(re.search(r"\bøko\b|økolog", f"{p.name} {p.underline}", re.IGNORECASE))


def _name(p: ShelfPrice) -> str:
    # REMA 1000 skriver "HK. OKSEKØD 8-12%" for hakket oksekød
    return re.sub(r"\bhk\.\s*", "hakket ", p.name, flags=re.IGNORECASE)


def _kg_price(p: ShelfPrice, key: str) -> float | None:
    """Prisen pr. kg (eller liter) som ingrediensen ``key``."""
    if not p.unit_price:
        return None
    if p.unit in ("kg", "l"):
        return p.unit_price
    piece = NORMAL_PRICES[key][1]
    return p.unit_price * 1000 / piece if p.unit == "stk" and piece else None


def basis_prices(prices: list[ShelfPrice]) -> dict[str, dict]:
    """Basisprisen for hver ingrediens, webshoppen har: {nøgle: {"price": kr
    pr. kg, "store", "product", "shelf": hyldeprisen, "pack"}}."""
    found: dict[str, list[tuple[float, ShelfPrice]]] = {}
    for p in prices:
        if _organic(p):
            continue
        name = _name(p)
        if any(_has_word(_tokens(f"{name} {p.underline}"), w) for w in _NOT_RAW):
            continue
        # Varen skal stå først i navnet: "Sky m/champignon" og "Naanbrød,
        # hvidløg" er ikke champignon og hvidløg
        head = re.split(r",|\bm/|\bmed\b", name, flags=re.IGNORECASE)[0].strip()
        keys = [key for pattern, key in _ALIASES if pattern.search(head)] or ingredient_keys(head)
        if len(keys) != 1 or p.department.casefold() not in DEPARTMENTS.get(department(keys[0]), set()):
            continue
        key = keys[0]
        kg = _kg_price(p, key)
        if kg and MIN_RATIO <= kg / NORMAL_PRICES[key][0] <= MAX_RATIO:
            found.setdefault(key, []).append((kg, p))
    result = {}
    for key, items in found.items():
        kg, p = min(items, key=lambda item: item[0])
        result[key] = {
            "price": round(kg, 2), "store": p.dealer, "product": p.name.capitalize(),
            "pack": p.underline.split("/")[0].strip().lower(), "shelf": p.price,
        }
    return result


def path_for(database: Path) -> Path:
    """Normalpriserne ligger ved siden af databasen med tilbuddene."""
    return Path(database).with_name(FILE_NAME)


def load(path: Path) -> tuple[list[ShelfPrice], datetime | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(data["fetched"]) if data.get("fetched") else None
        return [ShelfPrice.from_dict(p) for p in data.get("prices", [])], fetched
    except (OSError, ValueError, KeyError, TypeError):
        return [], None


def refresh(path: Path, now: datetime | None = None, force: bool = False) -> tuple[list[ShelfPrice], str | None]:
    """Henter normalpriserne igen, hvis de er for gamle, og gemmer dem i
    ``path``. Returnerer (priser, fejl); ved en fejl bruges de gamle priser."""
    now = now or datetime.now(timezone.utc)
    prices, fetched = load(path)
    if prices and fetched and not force and now - fetched < MAX_AGE:
        return prices, None
    try:
        fresh = fetch_shelf_prices()
    except SourceError as exc:
        return prices, str(exc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched": now.isoformat(), "prices": [p.to_dict() for p in fresh]},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return fresh, None
