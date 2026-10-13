"""Inddeling af tilbud i varekategorier ud fra nøgleord.

Kategorierne tjekkes i rækkefølge, og første match vinder. Derfor står de
mest specifikke kategorier (fx slik, hvor "mælkechokolade" ellers ville
ende under mejeri) før de brede.

Egne kategorier eller ekstra nøgleord kan tilføjes i konfigurationsfilen.
"""

from __future__ import annotations

import re
import unicodedata

UNCATEGORIZED = "andet"

DEFAULT_CATEGORIES: dict[str, dict] = {
    "slik_og_snacks": {
        "navn": "Slik & snacks",
        "noegleord": [
            "chokolade", "slik", "vingummi", "lakrids", "chips", "popcorn",
            "kiks", "småkager", "marabou", "haribo", "toms", "pringles",
            "nødder", "peanuts", "flødeboller", "karamel", "is ", "isvafler",
            "kage", "snack",
        ],
    },
    "drikkevarer": {
        "navn": "Drikkevarer",
        "noegleord": [
            "sodavand", "cola", "pepsi", "faxe kondi", "juice", "saft",
            "vand ", "kildevand", "danskvand", "sodavand", "energidrik", "smoothie", "iste",
        ],
    },
    "oel_og_vin": {
        "navn": "Øl, vin & spiritus",
        "noegleord": [
            "øl", "pilsner", "tuborg", "carlsberg", "rødvin", "hvidvin",
            "rosé", "vin ", "cava", "prosecco", "champagne", "spiritus",
            "vodka", "gin ", "whisky", "rom ", "cider",
        ],
    },
    "kaffe_og_te": {
        "navn": "Kaffe & te",
        "noegleord": ["kaffe", "espresso", "kaffebønner", "kapsler", "te ", "tebreve"],
    },
    "koed": {
        "navn": "Kød & fjerkræ",
        "noegleord": [
            "oksekød", "hakket", "kylling", "kalkun", "svinekød", "flæsk",
            "bacon", "mørbrad", "koteletter", "skinke", "medister", "pølser",
            "bøf", "steak", "steg", "okse", "culotte", "entrecote", "kalv", "lam ", "lammekød", "lammekølle", "and ",
            "andebryst", "frikadeller", "kyllingebryst", "kyllingelår",
            "nakkekoteletter", "ribbensteg", "spareribs", "kødpålæg",
            "leverpostej", "rullepølse", "salami", "pålæg", "kebab",
        ],
    },
    "fisk": {
        "navn": "Fisk & skaldyr",
        "noegleord": [
            "laks", "torsk", "fisk", "rejer", "tun ", "tunfisk", "makrel", "sild",
            "rødspætte", "kuller", "sej ", "fiskefrikadeller", "muslinger",
            "skaldyr", "hummer", "fiskefilet",
        ],
    },
    "mejeri": {
        "navn": "Mejeri & æg",
        "noegleord": [
            "mælk", "letmælk", "minimælk", "sødmælk", "yoghurt", "skyr",
            "ost", "smør", "fløde", "creme fraiche", "cremefraiche", "kærnemælk",
            "æg", "lurpak", "arla", "kvark", "hytteost", "piskefløde",
            "mozzarella", "feta", "parmesan", "riberhus", "smørbar",
        ],
    },
    "frugt_og_groent": {
        "navn": "Frugt & grønt",
        "noegleord": [
            "æbler", "æble", "pærer", "bananer", "banan", "appelsiner",
            "citroner", "druer", "vindruer", "jordbær", "blåbær", "hindbær", "melon",
            "avocado", "tomater", "agurk", "peberfrugt", "salat", "løg",
            "kartofler", "gulerødder", "broccoli", "blomkål", "squash",
            "champignon", "svampe", "porrer", "spinat", "kål", "frugt",
            "grøntsager", "mango", "ananas", "kiwi", "klementiner",
            "mandariner", "rødbeder", "hvidløg", "ingefær", "krydderurter",
        ],
    },
    "broed_og_bager": {
        "navn": "Brød & bageri",
        "noegleord": [
            "brød", "rugbrød", "franskbrød", "boller", "rundstykker",
            "toastbrød", "wienerbrød", "croissant", "bagel", "tortilla",
            "pitabrød", "knækbrød", "flutes", "baguette",
        ],
    },
    "frost": {
        "navn": "Frost",
        "noegleord": ["frost", "frossen", "frosne", "pizza", "pommes frites", "isbåde"],
    },
    "kolonial": {
        "navn": "Kolonial",
        "noegleord": [
            "pasta", "spaghetti", "ris", "mel", "sukker", "havregryn",
            "müsli", "mysli", "cornflakes", "morgenmad", "konserves",
            "flåede tomater", "bønner", "linser", "olie", "olivenolie",
            "eddike", "ketchup", "mayonnaise", "sennep", "krydderi",
            "bouillon", "sauce", "pesto", "honning", "marmelade",
            "syltetøj", "nutella", "peanutbutter", "nudler",
        ],
    },
    "husholdning": {
        "navn": "Husholdning",
        "noegleord": [
            "vaskemiddel", "opvask", "toiletpapir", "køkkenrulle",
            "rengøring", "skyllemiddel", "affaldsposer", "opvasketabs",
            "neutral", "ajax", "fairy", "vim", "stearinlys", "batterier",
        ],
    },
    "personlig_pleje": {
        "navn": "Personlig pleje",
        "noegleord": [
            "shampoo", "balsam", "tandpasta", "tandbørste", "deodorant",
            "sæbe", "showergel", "creme", "barberblade", "bind", "tamponer",
            "hudpleje", "makeup",
        ],
    },
    "baby": {
        "navn": "Baby",
        "noegleord": ["bleer", "babymad", "vådservietter", "libero", "pampers", "modermælk"],
    },
    "dyr": {
        "navn": "Kæledyr",
        "noegleord": ["hundemad", "kattemad", "kattegrus", "dyrefoder", "whiskas", "pedigree"],
    },
    "nonfood": {
        "navn": "Non-food",
        "noegleord": [
            "tv ", "fjernsyn", "telefon", "tøj ", "sko ", "legetøj", "værktøj",
            "møbler", "dyne", "pude", "sengetøj", "håndklæder", "gryde",
            "pande", "støvsuger", "kaffemaskine", "airfryer", "blomster",
            "potteplante", "cykel", "jakke", "bukser", "trøje",
        ],
    },
}

FOOD_CATEGORIES = {
    "koed", "fisk", "mejeri", "frugt_og_groent", "broed_og_bager", "frost",
    "kolonial", "slik_og_snacks", "drikkevarer", "kaffe_og_te",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


class Categorizer:
    """Tildeler kategori til et tilbud ud fra overskrift og beskrivelse.

    Danske ord er ofte sammensatte, og det bærende ord står sidst
    ("vandmelon" er en melon). Et nøgleord kan derfor matche et helt ord,
    slutningen af et ord eller begyndelsen af et ord - i den
    prioritetsrækkefølge. Længere nøgleord vinder over kortere, og ved
    lighed vinder kategorien, der står først.

    Et nøgleord med efterstillet mellemrum ("vin ") matcher kun hele ord.
    """

    def __init__(self, categories: dict[str, dict] | None = None) -> None:
        self.categories = categories if categories is not None else DEFAULT_CATEGORIES
        # (kategori, nøgleord-tokens, kun_hele_ord)
        self._keywords: list[tuple[str, tuple[str, ...], bool]] = []
        for key, spec in self.categories.items():
            for word in spec.get("noegleord", []):
                tokens = tuple(_tokens(word))
                if not tokens:
                    continue
                whole_only = word.endswith(" ") or len(tokens) > 1 or len(tokens[0]) < 3
                self._keywords.append((key, tokens, whole_only))

    def _best_match(self, text: str) -> str | None:
        tokens = _tokens(text)
        best_key, best_quality = None, 0
        for key, kw, whole_only in self._keywords:
            quality = 0
            if len(kw) > 1:
                for i in range(len(tokens) - len(kw) + 1):
                    if tuple(tokens[i : i + len(kw)]) == kw:
                        quality = sum(map(len, kw)) + 3
                        break
            else:
                word = kw[0]
                for token in tokens:
                    if token == word:
                        q = len(word) + 3
                    elif whole_only:
                        continue
                    elif token.endswith(word):
                        q = len(word) + 2
                    elif token.startswith(word):
                        q = len(word)
                    else:
                        continue
                    quality = max(quality, q)
            if quality > best_quality:
                best_key, best_quality = key, quality
        return best_key

    def categorize(self, heading: str, description: str = "") -> str:
        # Overskriften vægter højest: "Kyllingebryst - lækker til salat" er kød.
        return self._best_match(heading) or self._best_match(description) or UNCATEGORIZED

    def display_name(self, key: str | None) -> str:
        if key is None or key == UNCATEGORIZED:
            return "Andet"
        return self.categories.get(key, {}).get("navn", key)


def merge_categories(custom: dict[str, dict] | None) -> dict[str, dict]:
    """Fletter brugerens kategorier ind i standardkategorierne.

    Eksisterende kategorier får ekstra nøgleord; nye kategorier tilføjes
    forrest, så de vinder over standardkategorierne.
    """
    merged = {key: {**spec, "noegleord": list(spec["noegleord"])} for key, spec in DEFAULT_CATEGORIES.items()}
    new: dict[str, dict] = {}
    for key, spec in (custom or {}).items():
        words = list(spec.get("noegleord", []))
        if key in merged:
            merged[key]["noegleord"] = words + merged[key]["noegleord"]
            if "navn" in spec:
                merged[key]["navn"] = spec["navn"]
        else:
            new[key] = {"navn": spec.get("navn", key), "noegleord": words}
    return {**new, **merged}
