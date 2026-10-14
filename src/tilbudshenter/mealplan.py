"""Madplan ud fra ugens tilbud.

En fast samling af almindelige danske hverdagsretter, hvor hver
ingrediens kan genkendes i tilbudsaviserne. Hvert tilbud mærkes med de
ingredienser, det kan bruges som (``ingredient_keys``). Browseren vælger
så de retter, hvis hovedingrediens er på tilbud i brugerens butikker, og
viser hvilke tilbud retten kan laves af.

Retterne er til 4 personer; mængderne skaleres i browseren.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from .comparison import PRODUCT_GROUPS, _has_word, _tokens

# Ingrediens -> (navn, mønstre, udelukkelser). Samme form som
# comparison.PRODUCT_GROUPS: et mønster er en liste af ord, der alle skal
# stå i varenavnet, og et ord matcher også sammensatte ord, der begynder
# eller slutter med det, medmindre det slutter med mellemrum.
INGREDIENTS: dict[str, tuple[str, list[list[str]], list[str]]] = {
    # Kød
    "hakket_okse": PRODUCT_GROUPS["hakket_okse"],
    "hakket_gris": ("hakket grisekød", [*PRODUCT_GROUPS["hakket_gris"][1], ["hakket", "svinekød"]], ["kalv", "okse"]),
    # "Hakket kød" i en opskrift er som regel grise- og kalvekød
    "hakket_gris_kalv": ("hakket grise- og kalvekød", [*PRODUCT_GROUPS["hakket_gris_kalv"][1], ["hakket", "kød "],
                                                        ["hakket", "svine", "kalv"]],
                         PRODUCT_GROUPS["hakket_gris_kalv"][2]),
    "hakket_kylling": PRODUCT_GROUPS["hakket_kylling"],
    "kyllingebryst": ("kyllingebryst", [["kyllingebryst"], ["kyllingefilet"], ["kylling", "inderfilet"],
                                        ["kyllingeinderfilet"], ["kyllingestrimler"]], ["lage", "kalkun"]),
    "kyllingelaar": ("kyllingelår", [["kylling", "lår"], ["overlår"], ["underlår"]], ["and", "kalkun"]),
    "hel_kylling": ("hel kylling", [["hel", "kylling"], ["helkylling"], ["kylling", "hel "], ["kylling "]],
                    ["grill", "stegt", "lår", "bryst", "filet", "hakket", "pålæg", "kogt", "wings", "tern", "pose", "posen"]),
    "bacon": ("bacon", [["bacon"]], ["leverpostej", "kalkun", "pølse", "ost", "chips"]),
    "stegeflaesk": ("stegeflæsk", [["stegeflæsk"], ["brystflæsk"], ["flæsk", "skiver"]], ["svær", "steg"]),
    "medister": PRODUCT_GROUPS["medister"],
    "flaeskesteg": PRODUCT_GROUPS["flaeskesteg"],
    "moerbrad": ("mørbrad af gris", [*PRODUCT_GROUPS["moerbrad"][1], ["svinemørbrad"], ["mørbrader"]],
                 PRODUCT_GROUPS["moerbrad"][2]),
    "koteletter": ("koteletter", [["kotelet"]], ["lam", "kalv", "okse"]),
    "poelser": ("pølser", [["pølser"]], ["cocktail", "salami", "spege", "rulle", "leverpostej", "vegansk"]),
    "chorizo": ("chorizo", [["chorizo"]], ["chips", "snack", "pizza", "skiver"]),
    "boef": ("bøf", [["bøf "], ["bøffer"], ["oksebøf"], ["entrecote"], ["ribeye"], ["culotte"], ["flanksteak"],
                     ["oksefilet"]], ["hakke", "burger", "kylling", "kalkun", "lam", "lammekød", "gris", "vegansk", "plantebaseret"]),
    "okse_tern": ("oksekød i tern", [["okse", "tern"], ["gullasch"], ["oksegryde"], ["oksekødsstrimler"], ["oksestrimler"]],
                  ["kylling", "gris"]),
    # Fisk
    "laksefilet": ("laksefilet", [*PRODUCT_GROUPS["laksefilet"][1], ["laks "], ["lakseside"], ["laksesider"]], [*PRODUCT_GROUPS["laksefilet"][2], "skiver"]),
    "hvid_fisk": ("torsk eller anden hvid fisk", [["torsk"], ["sej "], ["sejfilet"], ["kuller"], ["rødspætte"],
                                                  ["fiskefilet"], ["pangasius"], ["hoki"]],
                  ["fars", "rogn", "lever", "frikadelle", "tørret", "røget"]),
    "fiskefrikadeller": ("fiskefrikadeller", [["fiskefrikadelle"], ["fiskefars"]], []),
    "tun": ("tun på dåse", [["tun "], ["tunfisk"]], ["salat", "mousse"]),
    "rejer": ("rejer", [["rejer"]], ["salat", "cocktail", "chips"]),
    # Mejeri og æg
    "aeg": PRODUCT_GROUPS["aeg"],
    "maelk": ("mælk", [["letmælk"], ["minimælk"], ["sødmælk"], ["skummetmælk"], ["kærnemælk"], ["mælk "]],
              ["kakao", "chokolade", "is "]),
    "floede": ("fløde", [["fløde "], ["piskefløde"], ["madlavningsfløde"], ["kogefløde"], ["cremefine"]],
               ["is ", "kaffe", "skum", "chokolade", "buko", "ost", "kartofler"]),
    "creme_fraiche": ("creme fraiche", [["creme", "fraiche"], ["cremefraiche"], ["fraiche"]], ["dressing"]),
    "revet_ost": ("revet ost", [["revet "], ["pizzaost"], ["mozzarella"], ["cheddar"]],
                  ["kokos", "rødbede", "citron", "gulerod", "chokolade", "snack", "sticks", "nuggets", "skiver"]),
    # Parmesan er dyrere end revet ost og kan ikke erstattes af pizzatopping
    "parmesan": ("parmesan", [["parmesan"], ["parmigiano"], ["grana", "padano"], ["pecorino"]],
                 ["chips", "snack", "kiks", "chili"]),
    "feta": ("feta", [["feta"], ["salatost"]], ["salat ", "oliven"]),
    "yoghurt": ("yoghurt eller skyr", [["yoghurt"], ["skyr"]],
                ["drik", "drikke", "is ", "müsli", "musli", "bar", "smoothie", "dressing", "frugt", "vanilje"]),
    "smoer": PRODUCT_GROUPS["smoer"],
    # Kolonial og brød
    "pasta": ("pasta", [["pasta "], ["spaghetti"], ["penne"], ["fusilli"], ["makaroni"], ["tagliatelle"],
                        ["farfalle"], ["rigatoni"], ["pastaskruer"]],
              ["salat", "lasagne", "græskar", "pesto", "tortellini", "ravioli", "fyldt"]),
    "lasagneplader": ("lasagneplader", [["lasagneplader"], ["lasagne", "plader"]], []),
    "ris": ("ris", [["ris "], ["jasminris"], ["basmatiris"], ["parboiled"], ["risottoris"]],
            ["grød", "kiks", "papir", "snack", "kage", "chips", "grødris"]),
    "nudler": ("nudler", [["nudler"]], ["suppe", "snack", "kop", "cup"]),
    "tortilla": ("tortillas", [["tortilla"], ["wraps"]], ["chips"]),
    "burgerboller": ("burgerboller", [["burgerbolle"], ["burgerbrød"], ["hamburgerbolle"], ["hamburgerbrød"]], []),
    "poelsebroed": ("pølsebrød", [["pølsebrød"], ["hotdogbrød"]], []),
    "pizzadej": ("pizzadej", [["pizzadej"], ["pizzabund"]], []),
    "hakkede_tomater": ("hakkede tomater", [["hakkede", "tomater"], ["flåede", "tomater"], ["passata"]], []),
    "kidneyboenner": ("kidneybønner", [["kidney"], ["chilibønner"], ["sorte", "bønner"]], []),
    "kokosmaelk": ("kokosmælk", [["kokosmælk"]], ["drik"]),
    "linser": ("linser", [["linser"]], ["chips", "snack", "suppe", "pasta"]),
    "majs": ("majs", [["majs "], ["majskerner"]], ["popcorn", "chips", "snack", "kolbe"]),
    # Frugt og grønt
    # Opskrifter skriver også ental: "1 gulerod", "300 g kartoffel", "2 stk tomat"
    "kartofler": ("kartofler", [*PRODUCT_GROUPS["kartofler"][1], ["kartoffel "], ["bagekartoffel"]],
                  [*PRODUCT_GROUPS["kartofler"][2], "sød ", "søde ", "sødkartof"]),
    "guleroedder": ("gulerødder", [*PRODUCT_GROUPS["guleroedder"][1], ["gulerod "]], PRODUCT_GROUPS["guleroedder"][2]),
    "loeg": ("løg", [["løg "], ["rødløg"], ["gule", "løg"]], ["ristede", "forårs", "purløg"]),
    "foraarsloeg": ("forårsløg", [["forårsløg"]], []),
    "hvidloeg": ("hvidløg", [["hvidløg "], ["hvidløgsfed"], ["hvidløgs ", "fed "]], ["dressing", "brød", "smør", "pølse", "gyros"]),
    "porrer": ("porrer", [["porre"]], []),
    "tomater": ("tomater", [*PRODUCT_GROUPS["tomater"][1], ["tomat "]], PRODUCT_GROUPS["tomater"][2]),
    "cherrytomater": ("cherrytomater", [["cherrytomat"], ["snacktomat"], ["cherry", "tomater"]], ["soltørrede", "dåse"]),
    "agurk": PRODUCT_GROUPS["agurk"],
    "peberfrugt": PRODUCT_GROUPS["peberfrugt"],
    "broccoli": PRODUCT_GROUPS["broccoli"],
    "blomkaal": ("blomkål", [["blomkål"]], ["broccoli", "ris"]),
    "spidskaal": ("spidskål eller hvidkål", [["spidskål"], ["hvidkål"]], []),
    "roedkaal": ("rødkål", [["rødkål"]], []),
    "champignon": ("champignon", [["champignon"]], []),
    "spinat": ("spinat", [["spinat"]], ["tærte", "pandekage", "ravioli"]),
    "salat": ("salat", [["iceberg"], ["hjertesalat"], ["salathoved"], ["hovedsalat"], ["salat "]], ["dressing"]),
    "romaine": ("romainesalat", [["romaine"]], ["dressing"]),
    "rucola": ("rucola", [["rucola"], ["ruccola"]], ["pesto", "dressing"]),
    "bladselleri": ("bladselleri", [["bladselleri"], ["stangselleri"], ["selleri"]], ["salt", "juice", "rod", "knold"]),
    "avocado": ("avocado", [["avocado"]], ["olie", "dip", "creme", "guacamole"]),
    "groenne_boenner": ("grønne bønner", [["grønne", "bønner"], ["haricots"], ["bønner", "haricot"]], []),
    "aerter": ("ærter", [["ærter "]], ["snack", "wasabi"]),
    "squash": ("squash", [["squash"], ["zucchini"], ["courgette"], ["courgetter"]], ["saft", "sodavand", "drik", "læske", "cl ", "tuborg", "faxe", "butternut", "spaghetti", "hokkaido", "græskar"]),
    "wokgroent": ("wokgrøntsager", [["wokgrønt"], ["wokblanding"]], []),
    "citron": ("citron", [["citroner"], ["citron "], ["citrusfrugt"]], ["saft", "juice", "te ", "vand", "kage", "is "]),
    "lime": ("lime", [["lime "], ["limefrugt"], ["limer "]], ["saft", "juice", "sodavand", "drik", "cider", "blade", "kaffir"]),
    "mango": ("mango", [["mango"]], ["juice", "chutney", "is ", "smoothie", "drik", "tørret", "lassi", "saft", "sorbet"]),
    "persille": ("persille", [["persille"]], ["pesto", "smør"]),
    "aebler": PRODUCT_GROUPS["aebler"],
}

# Basispris (kr pr. kg eller liter): den almindelige hyldepris uden tilbud
# på en almindelig vare, fx kædens eget mærke eller et kendt mærke i en
# discountbutik. Et tilbud bruges kun i madplanen, når det er billigere, og
# besparelsen regnes i forhold til den. Priserne er anslået ud fra
# hyldepriserne i 2026; ligger varen typisk dyrere i tilbudsaviserne, bruges
# det i stedet (se market_prices). Tallet efter prisen er vægten pr. stk,
# dåse, fed eller bundt i gram, til at omregne mellem stk og kg.
NORMAL_PRICES: dict[str, tuple[float, float]] = {
    "hakket_okse": (110, 500), "hakket_gris": (65, 500), "hakket_gris_kalv": (80, 500), "hakket_kylling": (90, 500),
    "kyllingebryst": (115, 150), "kyllingelaar": (45, 200), "hel_kylling": (60, 1400), "bacon": (110, 150),
    "chorizo": (180, 200), "stegeflaesk": (100, 400), "medister": (75, 500), "flaeskesteg": (65, 1500),
    "moerbrad": (110, 500), "koteletter": (85, 200), "poelser": (90, 60), "boef": (280, 150), "okse_tern": (180, 500),
    "laksefilet": (230, 125), "hvid_fisk": (200, 125), "fiskefrikadeller": (120, 60), "tun": (120, 185),
    "rejer": (220, 400),
    "aeg": (55, 60), "maelk": (14, 1000), "floede": (50, 250), "creme_fraiche": (45, 200), "revet_ost": (110, 175),
    "parmesan": (300, 150), "feta": (110, 200), "yoghurt": (25, 1000), "smoer": (110, 250),
    "pasta": (22, 500), "lasagneplader": (40, 250), "ris": (25, 1000), "nudler": (45, 250), "tortilla": (45, 40),
    "burgerboller": (50, 70), "poelsebroed": (40, 40), "pizzadej": (40, 400), "hakkede_tomater": (18, 400),
    "kidneyboenner": (22, 400), "kokosmaelk": (40, 400), "majs": (35, 300), "linser": (40, 500),
    "kartofler": (14, 100), "guleroedder": (12, 80), "loeg": (12, 150), "foraarsloeg": (80, 100), "hvidloeg": (80, 5),
    "porrer": (30, 250), "tomater": (40, 100), "cherrytomater": (70, 250), "agurk": (30, 400), "peberfrugt": (50, 200),
    "broccoli": (35, 400), "blomkaal": (30, 800), "spidskaal": (20, 1000), "roedkaal": (18, 500),
    "champignon": (70, 250), "spinat": (70, 250), "salat": (40, 400), "romaine": (50, 300), "rucola": (200, 65),
    "bladselleri": (35, 400), "avocado": (50, 200), "groenne_boenner": (40, 400), "aerter": (30, 450),
    "squash": (30, 300), "wokgroent": (35, 600), "citron": (40, 100), "lime": (60, 70), "mango": (40, 400),
    "persille": (150, 30), "aebler": (25, 150),
}

# Basisprisen følger tilbudsaviserne: koster en vare typisk mere på tilbud end
# basisprisen, er basisprisen for lav, og så bruges det typiske tilbud (højst
# halvanden gang basisprisen, så fejlgenkendte varer ikke trækker op).
MARKET_MIN_OFFERS = 6
MARKET_MAX_FACTOR = 1.5


def market_prices(offers) -> dict[str, float]:
    """Typisk pris pr. kg i tilbudsaviserne for hver ingrediens.

    ``offers`` er (overskrift, enhed, enhedspris) for tilbud, fx fra
    prishistorikken. Kun tilbud på én ingrediens, og kun ingredienser set i
    mindst MARKET_MIN_OFFERS tilbud, tæller.
    """
    per_key: dict[str, list[float]] = {}
    for heading, unit, unit_price in offers:
        keys = ingredient_keys(heading) if unit_price else []
        if len(keys) != 1:
            continue
        piece = NORMAL_PRICES[keys[0]][1]
        kg = unit_price if unit in ("kg", "l") else unit_price * 1000 / piece if unit == "stk" and piece else None
        if kg:
            per_key.setdefault(keys[0], []).append(kg)
    return {k: statistics.median(v) for k, v in per_key.items() if len(v) >= MARKET_MIN_OFFERS}


def basis_price(key: str, market: dict[str, float] | None = None) -> float:
    """Basisprisen i kr pr. kg, hævet til det typiske tilbud, hvis det er dyrere."""
    base = NORMAL_PRICES[key][0]
    typical = (market or {}).get(key)
    return float(round(max(base, min(typical, base * MARKET_MAX_FACTOR)))) if typical else float(base)


# Den mindste pakke af basisvaren i gram (eller ml), når den er større end ét
# stk: løg i net, æg i bakker, kartofler i poser. Ellers købes ét stk ad gangen.
# Madplanen bruger det til, hvad man betaler i butikken for varer uden tilbud.
BASIS_PACK_G: dict[str, float] = {
    "kyllingebryst": 500, "kyllingelaar": 1000, "poelser": 400, "koteletter": 600, "boef": 300, "laksefilet": 250,
    "hvid_fisk": 400, "fiskefrikadeller": 300, "aeg": 600, "tortilla": 320, "burgerboller": 280, "poelsebroed": 400,
    "lasagneplader": 500, "kartofler": 2000, "guleroedder": 1000, "loeg": 1000, "hvidloeg": 150, "tomater": 500,
    "citron": 300, "lime": 210, "aebler": 1000,
}


def basis_pack_g(key: str) -> float:
    return BASIS_PACK_G.get(key) or NORMAL_PRICES[key][1]


# Ord der betyder, at tilbuddet ikke er en råvare
_NOT_RAW = [
    "færdigret", "pålæg", "suppe", "sauce", "dressing", "chips", "snack", "juice", "spyd", "kebab",
    "gratin", "fyld", "smoothie", "grillet", "salatbar", "ravioli", "pizza ",
]
# Ord der gælder hele tilbuddet, også når det nævner flere varer
# ("Syltede rødløg, agurker eller aioli", "æble- eller pærecidereddike",
# "Indbagt laks med spinat eller rejer med asparges")
_NOT_RAW_HEADING = ["syltede", "eddike", "indbagt"]


@dataclass
class Item:
    amount: float  # til 4 personer; 0 = efter smag
    unit: str  # "g", "stk", "dåse", "dl" ...
    name: str
    keys: list[str] = field(default_factory=list)  # ingredienser fra INGREDIENTS
    main: bool = False  # retten foreslås kun, når en hovedingrediens er på tilbud


@dataclass
class Recipe:
    id: str
    name: str
    kind: str  # okse, gris, kylling, fisk eller vegetar
    minutes: int
    items: list[Item]
    pantry: list[str]  # typisk derhjemme: krydderier, olie, mel ...
    method: str
    source: str = ""  # madsiden, opskriften er hentet fra
    flags: list[str] = field(default_factory=list)  # "pork", "fish" eller "meat" i fx bouillon


def I(amount: float, unit: str, name: str, keys: str = "", main: bool = False) -> Item:  # noqa: E743
    return Item(amount, unit, name, keys.split("|") if keys else [], main)


RECIPES: list[Recipe] = [
    # -- Okse --------------------------------------------------------------
    Recipe("bolognese", "Spaghetti bolognese", "okse", 40, [
        I(500, "g", "hakket kød (okse eller grise- og kalv)", "hakket_okse|hakket_gris_kalv", True),
        I(400, "g", "spaghetti", "pasta"),
        I(2, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(1, "stk", "løg", "loeg"),
        I(2, "stk", "gulerødder", "guleroedder"),
        I(2, "fed", "hvidløg", "hvidloeg"),
    ], ["olie", "tomatpuré", "oregano", "salt og peber"],
        "Svits hakket løg, hvidløg og revne gulerødder, og brun kødet. Tilsæt tomater og tomatpuré, "
        "og lad sovsen simre 20 minutter. Server med spaghetti."),
    Recipe("lasagne", "Lasagne", "okse", 75, [
        I(500, "g", "hakket kød (okse eller grise- og kalv)", "hakket_okse|hakket_gris_kalv", True),
        I(250, "g", "lasagneplader", "lasagneplader"),
        I(2, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(1, "stk", "løg", "loeg"),
        I(2, "stk", "gulerødder", "guleroedder"),
        I(5, "dl", "mælk", "maelk"),
        I(150, "g", "revet ost", "revet_ost"),
    ], ["smør", "hvedemel", "olie", "salt og peber"],
        "Lav kødsovs af kød, løg, gulerødder og tomater. Lav en hvid sovs af smør, mel og mælk. "
        "Læg plader, kødsovs og hvid sovs i lag, drys med ost og bag 40 minutter ved 200 grader."),
    Recipe("chili", "Chili con carne med ris", "okse", 45, [
        I(500, "g", "hakket oksekød", "hakket_okse", True),
        I(1, "dåse", "kidneybønner", "kidneyboenner"),
        I(2, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(1, "stk", "løg", "loeg"),
        I(1, "stk", "peberfrugt", "peberfrugt"),
        I(300, "g", "ris", "ris"),
        I(2, "dl", "creme fraiche", "creme_fraiche"),
    ], ["chili", "spidskommen", "olie", "salt og peber"],
        "Brun kødet med løg og peberfrugt, krydr med chili og spidskommen. Tilsæt tomater og bønner, "
        "og lad det simre 25 minutter. Server med ris og creme fraiche."),
    Recipe("tacos", "Tacos", "okse", 25, [
        I(500, "g", "hakket kød (okse eller grise- og kalv)", "hakket_okse|hakket_gris_kalv", True),
        I(8, "stk", "tortillas", "tortilla"),
        I(1, "stk", "salathoved", "salat"),
        I(3, "stk", "tomater", "tomater"),
        I(1, "stk", "agurk", "agurk"),
        I(1, "dåse", "majs", "majs"),
        I(150, "g", "revet ost", "revet_ost"),
        I(2, "dl", "creme fraiche", "creme_fraiche"),
    ], ["tacokrydderi", "olie"],
        "Brun kødet og krydr det med tacokrydderi og lidt vand. Skær grøntsagerne ud, "
        "og lad alle fylde deres egne tortillas."),
    Recipe("burger", "Burgere", "okse", 30, [
        I(600, "g", "hakket oksekød", "hakket_okse", True),
        I(4, "stk", "burgerboller", "burgerboller"),
        I(1, "stk", "salathoved", "salat"),
        I(2, "stk", "tomater", "tomater"),
        I(1, "stk", "rødløg", "loeg"),
        I(1, "stk", "agurk", "agurk"),
        I(100, "g", "bacon", "bacon"),
    ], ["ketchup", "mayonnaise", "salt og peber"],
        "Form fire bøffer og steg dem 3-4 minutter på hver side sammen med baconen. "
        "Rist bollerne, og byg burgerne med salat, tomat, løg og agurk."),
    Recipe("hakkeboef", "Hakkebøf med bløde løg og kartofler", "okse", 40, [
        I(600, "g", "hakket oksekød", "hakket_okse", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(4, "stk", "løg", "loeg"),
        I(300, "g", "ærter", "aerter"),
    ], ["smør", "sovsekulør", "hvedemel", "salt og peber"],
        "Kog kartoflerne. Steg bøfferne, og steg løgene bløde i fedtet bagefter. "
        "Kog fedtet op med vand til en sovs, og server med ærter."),
    Recipe("boef", "Bøf med kartoffelbåde og salat", "okse", 45, [
        I(600, "g", "bøf", "boef", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(1, "stk", "salathoved", "salat"),
        I(3, "stk", "tomater", "tomater"),
        I(1, "stk", "agurk", "agurk"),
    ], ["olie", "smør", "salt og peber"],
        "Skær kartoflerne i både, vend dem i olie og salt, og bag dem 35 minutter ved 220 grader. "
        "Steg bøfferne 2-4 minutter på hver side og lad dem hvile. Server med salat."),
    Recipe("gullasch", "Gullasch med kartoffelmos", "okse", 120, [
        I(800, "g", "oksekød i tern", "okse_tern", True),
        I(2, "stk", "løg", "loeg"),
        I(2, "stk", "peberfrugt", "peberfrugt"),
        I(1, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(1200, "g", "kartofler", "kartofler"),
        I(2, "dl", "mælk", "maelk"),
    ], ["paprika", "bouillon", "smør", "salt og peber"],
        "Brun kødet i en gryde, tilsæt løg, paprika, tomater og bouillon, og lad det simre to timer under låg. "
        "Tilsæt peberfrugt den sidste halve time. Mos de kogte kartofler med smør og mælk."),
    # -- Gris --------------------------------------------------------------
    Recipe("frikadeller", "Frikadeller med kartofler og rødkål", "gris", 50, [
        I(500, "g", "hakket grise- og kalvekød", "hakket_gris_kalv|hakket_gris", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(1, "stk", "løg", "loeg"),
        I(1, "stk", "æg", "aeg"),
        I(1, "dl", "mælk", "maelk"),
        I(500, "g", "rødkål", "roedkaal"),
    ], ["hvedemel", "smør", "salt og peber"],
        "Rør farsen med revet løg, æg, mel, mælk, salt og peber. Steg frikadellerne 5-6 minutter på hver side. "
        "Server med kogte kartofler, rødkål og eventuelt brun sovs."),
    Recipe("boller_i_karry", "Boller i karry med ris", "gris", 50, [
        I(500, "g", "hakket grisekød", "hakket_gris|hakket_gris_kalv", True),
        I(300, "g", "ris", "ris"),
        I(2, "stk", "løg", "loeg"),
        I(1, "stk", "æble", "aebler"),
        I(1, "stk", "æg", "aeg"),
        I(1, "dl", "fløde", "floede"),
    ], ["karry", "smør", "hvedemel", "bouillon", "salt og peber"],
        "Rør farsen med æg, mel og salt, og kog små boller i saltet vand. Svits løg og karry i smør, "
        "jævn med mel og kogevandet, og tilsæt fløde og æble. Server med ris."),
    Recipe("stegt_flaesk", "Stegt flæsk med persillesovs", "gris", 45, [
        I(800, "g", "stegeflæsk", "stegeflaesk", True),
        I(1200, "g", "kartofler", "kartofler"),
        I(5, "dl", "mælk", "maelk"),
        I(1, "bundt", "persille", "persille"),
    ], ["smør", "hvedemel", "salt og peber"],
        "Steg flæsket sprødt på panden eller i ovnen ved 220 grader. Kog kartoflerne. "
        "Lav en hvid sovs af smør, mel og mælk, og rør hakket persille i."),
    Recipe("braendende_kaerlighed", "Brændende kærlighed", "gris", 40, [
        I(250, "g", "bacon i tern", "bacon", True),
        I(1200, "g", "kartofler", "kartofler"),
        I(3, "stk", "løg", "loeg"),
        I(2, "dl", "mælk", "maelk"),
    ], ["smør", "rødbeder", "salt og peber"],
        "Kog kartoflerne og mos dem med smør og varm mælk. Steg bacon og løg gyldne, "
        "og læg dem over mosen. Server med rødbeder."),
    Recipe("medister", "Medister med kartofler og rødkål", "gris", 40, [
        I(600, "g", "medister", "medister", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(500, "g", "rødkål", "roedkaal"),
    ], ["smør", "salt og peber"],
        "Steg medisteren ved middel varme 20-25 minutter, og vend den undervejs. "
        "Server med kogte kartofler, rødkål og sovs af stegefedtet."),
    Recipe("flaeskesteg", "Flæskesteg med brune kartofler", "gris", 120, [
        I(1500, "g", "flæskesteg", "flaeskesteg", True),
        I(1200, "g", "kartofler", "kartofler"),
        I(500, "g", "rødkål", "roedkaal"),
    ], ["salt", "laurbærblade", "sukker", "smør", "sovsekulør"],
        "Gnid sværen med salt, og steg stegen ved 200 grader i cirka 1,5 time, til kernen er 65 grader. "
        "Giv den 10 minutter ved 250 grader til sprød svær. Server med brune og hvide kartofler og rødkål."),
    Recipe("moerbradgryde", "Mørbradgryde med ris", "gris", 35, [
        I(600, "g", "svinemørbrad", "moerbrad", True),
        I(250, "g", "champignon", "champignon"),
        I(2.5, "dl", "fløde", "floede"),
        I(1, "stk", "løg", "loeg"),
        I(300, "g", "ris", "ris"),
    ], ["paprika", "bouillon", "smør", "salt og peber"],
        "Skær mørbraden i skiver, og brun dem med løg og champignon. Tilsæt fløde, paprika og bouillon, "
        "og lad det simre 10 minutter. Server med ris."),
    Recipe("koteletter", "Koteletter med kartofler og grønne bønner", "gris", 35, [
        I(800, "g", "koteletter", "koteletter", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(400, "g", "grønne bønner", "groenne_boenner"),
    ], ["smør", "salt og peber"],
        "Steg koteletterne 4-5 minutter på hver side. Kog kartofler og bønner, "
        "og lav en hurtig sovs på stegefedtet."),
    Recipe("hotdogs", "Hotdogs", "gris", 15, [
        I(8, "stk", "pølser", "poelser", True),
        I(8, "stk", "pølsebrød", "poelsebroed"),
        I(1, "stk", "løg", "loeg"),
        I(1, "stk", "agurk", "agurk"),
    ], ["ketchup", "sennep", "remoulade", "ristede løg"],
        "Varm pølserne i vand eller på panden, og lun brødene i ovnen. "
        "Server med hakket løg, agurkesalat og det hele."),
    Recipe("carbonara", "Pasta carbonara", "gris", 20, [
        I(250, "g", "bacon", "bacon", True),
        I(400, "g", "spaghetti", "pasta"),
        I(3, "stk", "æg", "aeg"),
        I(75, "g", "revet ost", "revet_ost"),
    ], ["salt og peber"],
        "Kog pastaen, og steg baconen sprød. Pisk æg og ost sammen, og vend det med den varme pasta "
        "og baconen væk fra varmen, så æggene ikke koagulerer. Krydr med peber."),
    Recipe("aeggekage", "Æggekage med bacon", "gris", 25, [
        I(8, "stk", "æg", "aeg", True),
        I(200, "g", "bacon", "bacon", True),
        I(3, "stk", "tomater", "tomater"),
        I(1, "dl", "mælk", "maelk"),
    ], ["purløg", "rugbrød", "salt og peber"],
        "Steg baconen sprød. Pisk æg og mælk sammen, og lad æggekagen stivne på panden ved lav varme. "
        "Læg bacon og tomatskiver på, og server med rugbrød."),
    # -- Kylling -----------------------------------------------------------
    Recipe("kylling_karry", "Kylling i karry med ris", "kylling", 35, [
        I(600, "g", "kyllingebryst", "kyllingebryst|kyllingelaar", True),
        I(300, "g", "ris", "ris"),
        I(1, "stk", "løg", "loeg"),
        I(1, "stk", "peberfrugt", "peberfrugt"),
        I(1, "dåse", "kokosmælk", "kokosmaelk"),
        I(1, "stk", "broccoli", "broccoli"),
    ], ["karry", "olie", "salt"],
        "Steg kyllingen i strimler med løg og karry. Tilsæt kokosmælk, peberfrugt og broccoli, "
        "og lad det simre 10 minutter. Server med ris."),
    Recipe("wok", "Wok med kylling og nudler", "kylling", 25, [
        I(500, "g", "kyllingebryst", "kyllingebryst", True),
        I(250, "g", "nudler", "nudler"),
        I(600, "g", "wokgrøntsager", "wokgroent|broccoli|peberfrugt"),
        I(2, "fed", "hvidløg", "hvidloeg"),
    ], ["soja", "olie", "ingefær"],
        "Kog nudlerne. Steg kyllingestrimler ved høj varme, tilsæt hvidløg og grøntsager, "
        "og vend nudler og soja i til sidst."),
    Recipe("kyllingelaar", "Ovnstegte kyllingelår med kartofler", "kylling", 55, [
        I(1200, "g", "kyllingelår", "kyllingelaar", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(500, "g", "gulerødder", "guleroedder"),
        I(2, "stk", "løg", "loeg"),
    ], ["olie", "paprika", "timian", "salt og peber"],
        "Læg lår, kartofler, gulerødder og løg i både i et fad. Vend med olie og krydderier, "
        "og bag det hele 45 minutter ved 200 grader."),
    Recipe("hel_kylling", "Hel kylling i ovn med agurkesalat", "kylling", 90, [
        I(1400, "g", "hel kylling", "hel_kylling", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(1, "stk", "agurk", "agurk"),
        I(1, "stk", "citron", "citron"),
    ], ["smør", "eddike", "sukker", "salt og peber"],
        "Gnid kyllingen med smør, salt og peber, og læg citronen i den. Steg den 1 time og 15 minutter ved "
        "200 grader. Server med kartofler og agurkesalat."),
    Recipe("kylling_wraps", "Wraps med kylling", "kylling", 25, [
        I(500, "g", "kyllingebryst", "kyllingebryst", True),
        I(8, "stk", "tortillas", "tortilla"),
        I(1, "stk", "salathoved", "salat"),
        I(3, "stk", "tomater", "tomater"),
        I(1, "stk", "agurk", "agurk"),
        I(2, "dl", "creme fraiche", "creme_fraiche"),
    ], ["paprika", "olie", "salt og peber"],
        "Steg kyllingen i strimler med paprika. Skær grøntsagerne ud, "
        "og fyld wrapsene med kylling, salat og creme fraiche."),
    Recipe("kylling_pasta", "Cremet pasta med kylling", "kylling", 30, [
        I(500, "g", "kyllingebryst", "kyllingebryst", True),
        I(400, "g", "pasta", "pasta"),
        I(2.5, "dl", "fløde", "floede"),
        I(250, "g", "champignon", "champignon"),
        I(100, "g", "spinat", "spinat"),
        I(50, "g", "revet ost", "revet_ost"),
    ], ["bouillon", "olie", "salt og peber"],
        "Steg kylling og champignon, tilsæt fløde og bouillon, og lad det koge lidt ind. "
        "Vend spinat, ost og den kogte pasta i."),
    Recipe("kyllingefrikadeller", "Kyllingefrikadeller med kartofler og råkost", "kylling", 45, [
        I(500, "g", "hakket kyllingekød", "hakket_kylling", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(500, "g", "gulerødder", "guleroedder"),
        I(1, "stk", "løg", "loeg"),
        I(1, "stk", "æg", "aeg"),
    ], ["hvedemel", "smør", "rosiner", "salt og peber"],
        "Rør farsen med revet løg, æg og mel, og steg frikadellerne 5 minutter på hver side. "
        "Server med kartofler og revne gulerødder."),
    Recipe("caesar", "Cæsarsalat med kylling", "kylling", 25, [
        I(500, "g", "kyllingebryst", "kyllingebryst", True),
        I(2, "stk", "romainesalat", "romaine"),
        I(100, "g", "bacon", "bacon"),
        I(50, "g", "revet ost", "revet_ost"),
    ], ["brød til croutoner", "mayonnaise", "citron", "salt og peber"],
        "Steg kyllingen og baconen, og rist brødterninger på panden. "
        "Vend salaten med dressing af mayonnaise og citron, og top med kylling, bacon og ost."),
    # -- Fisk --------------------------------------------------------------
    Recipe("laks_ovn", "Laks i ovn med kartofler og broccoli", "fisk", 35, [
        I(600, "g", "laksefilet", "laksefilet", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(1, "stk", "broccoli", "broccoli"),
        I(1, "stk", "citron", "citron"),
    ], ["olie", "dild", "salt og peber"],
        "Læg laksen i et fad med citronskiver, salt og peber, og bag den 15-18 minutter ved 200 grader. "
        "Server med kogte kartofler og broccoli."),
    Recipe("stegt_fisk", "Stegt fisk med persillesovs", "fisk", 35, [
        I(600, "g", "torsk eller anden hvid fisk", "hvid_fisk", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(4, "dl", "mælk", "maelk"),
        I(1, "bundt", "persille", "persille"),
        I(1, "stk", "citron", "citron"),
    ], ["rasp", "smør", "hvedemel", "salt og peber"],
        "Vend fisken i rasp, og steg den gylden i smør. Lav en hvid sovs af smør, mel og mælk med hakket persille. "
        "Server med kartofler og citron."),
    Recipe("fiskefrikadeller", "Fiskefrikadeller med kartofler og råkost", "fisk", 30, [
        I(600, "g", "fiskefrikadeller", "fiskefrikadeller", True),
        I(1000, "g", "kartofler", "kartofler"),
        I(500, "g", "gulerødder", "guleroedder"),
        I(1, "stk", "citron", "citron"),
    ], ["remoulade", "smør"],
        "Steg fiskefrikadellerne gyldne på panden, eller form dem selv af fars. "
        "Server med kartofler, revne gulerødder, remoulade og citron."),
    Recipe("laks_pasta", "Pasta med laks og spinat", "fisk", 25, [
        I(400, "g", "laksefilet", "laksefilet", True),
        I(400, "g", "pasta", "pasta"),
        I(2.5, "dl", "fløde", "floede"),
        I(150, "g", "spinat", "spinat"),
        I(1, "stk", "citron", "citron"),
    ], ["hvidløg", "salt og peber"],
        "Steg laksen i tern, tilsæt fløde, revet citronskal og spinat, og lad det simre et par minutter. "
        "Vend den kogte pasta i."),
    Recipe("tunpasta", "Pastasalat med tun", "fisk", 20, [
        I(2, "dåse", "tun", "tun", True),
        I(400, "g", "pasta", "pasta"),
        I(1, "dåse", "majs", "majs"),
        I(1, "stk", "peberfrugt", "peberfrugt"),
        I(2, "dl", "creme fraiche", "creme_fraiche"),
    ], ["citron", "salt og peber"],
        "Kog pastaen og skyl den kold. Vend den med tun, majs, peberfrugt i tern og creme fraiche, "
        "og smag til med citron, salt og peber."),
    Recipe("rejepasta", "Pasta med rejer og hvidløg", "fisk", 20, [
        I(400, "g", "rejer", "rejer", True),
        I(400, "g", "spaghetti", "pasta"),
        I(3, "fed", "hvidløg", "hvidloeg"),
        I(1, "stk", "citron", "citron"),
        I(250, "g", "tomater", "tomater"),
    ], ["olivenolie", "chili", "salt og peber"],
        "Kog pastaen. Steg hvidløg, chili og tomater i olie, tilsæt rejerne til sidst, "
        "og vend det hele med pasta og citron."),
    # -- Vegetar -----------------------------------------------------------
    Recipe("veg_chili", "Vegetarisk chili med ris", "vegetar", 35, [
        I(2, "dåse", "kidneybønner", "kidneyboenner", True),
        I(2, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(2, "stk", "peberfrugt", "peberfrugt"),
        I(1, "stk", "løg", "loeg"),
        I(1, "dåse", "majs", "majs"),
        I(300, "g", "ris", "ris"),
    ], ["chili", "spidskommen", "olie", "salt og peber"],
        "Svits løg og peberfrugt med krydderierne, tilsæt tomater, bønner og majs, "
        "og lad det simre 20 minutter. Server med ris."),
    Recipe("shakshuka", "Shakshuka", "vegetar", 25, [
        I(8, "stk", "æg", "aeg", True),
        I(2, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(2, "stk", "peberfrugt", "peberfrugt"),
        I(1, "stk", "løg", "loeg"),
        I(100, "g", "feta", "feta"),
    ], ["spidskommen", "paprika", "olie", "brød", "salt og peber"],
        "Svits løg og peberfrugt, tilsæt tomater og krydderier, og lad det koge lidt ind. "
        "Slå æggene ud i sovsen, læg låg på, og drys med feta, når æggene er stivnede."),
    Recipe("pizza", "Hjemmelavet pizza", "vegetar", 40, [
        I(200, "g", "revet ost", "revet_ost", True),
        I(2, "stk", "pizzadej", "pizzadej"),
        I(1, "dåse", "hakkede tomater", "hakkede_tomater"),
        I(250, "g", "champignon", "champignon"),
        I(1, "stk", "peberfrugt", "peberfrugt"),
    ], ["oregano", "olie", "salt"],
        "Rul dejen ud, smør tomat på, og fordel grøntsager og ost. "
        "Bag pizzaerne 12-15 minutter ved 250 grader."),
    Recipe("kartoffelsuppe", "Kartoffel- og porresuppe", "vegetar", 35, [
        I(1000, "g", "kartofler", "kartofler", True),
        I(3, "stk", "porrer", "porrer", True),
        I(2, "dl", "fløde", "floede"),
        I(100, "g", "bacon", "bacon"),
    ], ["bouillon", "smør", "brød", "salt og peber"],
        "Svits porrerne i smør, tilsæt kartofler i tern og bouillon, og kog 20 minutter. "
        "Blend suppen, rør fløden i, og top med sprød bacon."),
    Recipe("risotto", "Svamperisotto", "vegetar", 35, [
        I(400, "g", "champignon", "champignon", True),
        I(300, "g", "risottoris", "ris"),
        I(1, "stk", "løg", "loeg"),
        I(75, "g", "revet ost", "revet_ost"),
        I(50, "g", "smør", "smoer"),
    ], ["bouillon", "hvidvin", "salt og peber"],
        "Svits løg og ris, og tilsæt varm bouillon lidt ad gangen under omrøring i 18-20 minutter. "
        "Steg svampene for sig, og vend dem i med smør og ost til sidst."),
    Recipe("blomkaal", "Ovnbagt blomkål med feta og kartofler", "vegetar", 45, [
        I(1, "stk", "blomkål", "blomkaal", True),
        I(800, "g", "kartofler", "kartofler"),
        I(150, "g", "feta", "feta"),
        I(250, "g", "tomater", "tomater"),
    ], ["olie", "spidskommen", "salt og peber"],
        "Skær blomkål og kartofler i stykker, vend dem i olie og krydderier, og bag dem 35 minutter ved "
        "220 grader. Top med smuldret feta og tomater."),
    Recipe("squash_pasta", "Pasta med squash og citron", "vegetar", 25, [
        I(2, "stk", "squash", "squash", True),
        I(400, "g", "pasta", "pasta"),
        I(2, "fed", "hvidløg", "hvidloeg"),
        I(1, "stk", "citron", "citron"),
        I(75, "g", "revet ost", "revet_ost"),
    ], ["olivenolie", "chili", "salt og peber"],
        "Riv eller skær squashen i tynde strimler, og steg den med hvidløg og chili. "
        "Vend med pasta, citronskal, citronsaft og ost."),
]


def _parts(heading: str) -> list[str]:
    parts = [p.strip() for p in re.split(r",|\beller\b", heading, flags=re.IGNORECASE)]
    return [p for p in parts if p and not p.startswith("-")]


def _matches(tokens: list[str], spec: tuple[str, list[list[str]], list[str]]) -> bool:
    _, patterns, exclude = spec
    if any(_has_word(tokens, w) for w in exclude):
        return False
    return any(all(_has_word(tokens, w) for w in pattern) for pattern in patterns)


# Mere præcise ingredienser, der vinder over en bredere: står der
# "revet parmesan", er det parmesan og ikke en hvilken som helst revet ost
REPLACES = {"parmesan": ["revet_ost"], "romaine": ["salat"], "rucola": ["salat"], "cherrytomater": ["tomater"],
            "foraarsloeg": ["loeg"]}


# Første ord i hvert mønster. Står ingen af dem i varenavnet, kan
# ingrediensen ikke matche, og den dyrere kontrol springes over.
_TRIGGERS = {
    key: [pattern[0].strip().casefold() for pattern in spec[1]] for key, spec in INGREDIENTS.items()
}


def ingredient_keys(heading: str) -> list[str]:
    """De ingredienser, et tilbud kan bruges som, fx ["hakket_okse"].

    Nævner varenavnet flere varer ("Kyllingebryst eller kyllingelår"),
    tæller hver af dem.
    """
    return list(_ingredient_keys(heading))


def ingredient_names(heading: str) -> dict[str, str]:
    """Den del af varenavnet, hver ingrediens står i, når tilbuddet nævner
    flere varer: "Xtra! pasta eller Coop hakkede tomater" giver
    {"pasta": "Xtra! pasta", "hakkede_tomater": "Coop hakkede tomater"}.
    Tom, når alle ingredienser står i samme del."""
    keys = ingredient_keys(heading)
    names = {}
    for part in _parts(heading):
        for key in _ingredient_keys(part):
            if key in keys and key not in names:
                names[key] = part
    return names if len(set(names.values())) > 1 else {}


@lru_cache(maxsize=8192)
def _ingredient_keys(heading: str) -> tuple[str, ...]:
    found: list[str] = []
    if any(_has_word(_tokens(heading), w) for w in _NOT_RAW_HEADING):
        return ()
    for part in _parts(heading):
        text = part.casefold()
        candidates = [key for key, words in _TRIGGERS.items() if any(w in text for w in words)]
        if not candidates:
            continue
        tokens = _tokens(part)
        if any(_has_word(tokens, w) for w in _NOT_RAW):
            continue
        here = [key for key in candidates if _matches(tokens, INGREDIENTS[key])]
        replaced = {r for k in here for r in REPLACES.get(k, [])}
        found += [k for k in here if k not in replaced and k not in found]
    return tuple(found)


def _amount(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


# Grøntsager og bælgfrugter, der tæller med i "grønt pr. person".
# Kartofler tæller ikke med, ligesom i Fødevarestyrelsens kostråd.
VEGETABLES = {
    "guleroedder", "loeg", "porrer", "tomater", "hakkede_tomater", "agurk", "peberfrugt", "broccoli",
    "blomkaal", "spidskaal", "roedkaal", "champignon", "spinat", "salat", "groenne_boenner", "aerter",
    "squash", "wokgroent", "majs", "kidneyboenner", "cherrytomater", "romaine", "rucola", "bladselleri", "avocado",
    "foraarsloeg", "linser",
}

# Kostrådene anbefaler omkring 600 g frugt og grønt om dagen. En ret med
# mindre end dette pr. person får en portion grønt tilbehør.
MIN_VEG_PER_PERSON = 125

# Tilbehøret: det billigste af disse, der er på tilbud
SIDE = Item(500, "g", "grønt tilbehør, fx råkost, salat eller dampet broccoli",
            ["guleroedder", "spidskaal", "broccoli", "agurk", "tomater", "salat", "groenne_boenner", "aerter"])


def _grams(item: Item) -> float:
    if item.unit == "g":
        return item.amount
    if item.unit == "dl":
        return item.amount * 100
    return item.amount * NORMAL_PRICES[item.keys[0]][1]


def vegetables_per_person(items: list[Item]) -> float:
    """Gram grøntsager pr. person i en ret til 4."""
    return sum(_grams(i) for i in items if i.keys and i.keys[0] in VEGETABLES) / 4


def recipe_items(recipe: Recipe) -> list[Item]:
    """Rettens varer, med grønt tilbehør hvis den har for lidt grønt."""
    if vegetables_per_person(recipe.items) >= MIN_VEG_PER_PERSON:
        return recipe.items
    return [*recipe.items, SIDE]


def _item_payload(i: Item) -> dict:
    return {
        "amount": _amount(i.amount), "unit": i.unit, "name": i.name, "keys": i.keys, "main": i.main,
        "side": i is SIDE,
        # Basispris pr. kg og vægt pr. stk for hver ingrediens
        "prices": {k: list(NORMAL_PRICES[k]) for k in i.keys},
    }


def _recipe_payload(r: Recipe) -> dict:
    items = recipe_items(r)
    return {
        "id": r.id,
        "name": r.name,
        "kind": r.kind,
        "minutes": r.minutes,
        "items": [_item_payload(i) for i in items],
        "veg_g": int(vegetables_per_person(items) + 0.5),  # rundes som i browseren
        "pantry": r.pantry,
        "method": r.method,
        **({"source": r.source} if r.source else {}),
        **({"flags": r.flags} if r.flags else {}),
    }


def recipes_payload() -> list[dict]:
    """Retterne som siden og appen bruger dem: de faste og dem fra madsiderne."""
    return [_recipe_payload(r) for r in [*RECIPES, *imported_recipes()]]


# -- Afdelinger ---------------------------------------------------------
# Hvor i butikken ingrediensen står (samme navne som kategorierne), så
# indkøbslisten kan følge vejen gennem butikken
_DEPARTMENT_KEYS = {
    "koed": ["hakket_okse", "hakket_gris", "hakket_gris_kalv", "hakket_kylling", "kyllingebryst", "kyllingelaar",
             "hel_kylling", "bacon", "stegeflaesk", "medister", "flaeskesteg", "moerbrad", "koteletter", "poelser",
             "boef", "okse_tern", "chorizo"],
    "fisk": ["laksefilet", "hvid_fisk", "fiskefrikadeller", "rejer"],
    "mejeri": ["aeg", "maelk", "floede", "creme_fraiche", "revet_ost", "parmesan", "feta", "yoghurt", "smoer",
               "pizzadej"],
    "broed_og_bager": ["tortilla", "burgerboller", "poelsebroed"],
    "frost": ["aerter", "wokgroent"],
    "kolonial": ["pasta", "lasagneplader", "ris", "nudler", "hakkede_tomater", "kidneyboenner", "kokosmaelk",
                 "majs", "tun", "linser"],
}
DEPARTMENTS = {k: dept for dept, keys in _DEPARTMENT_KEYS.items() for k in keys}


def department(key: str) -> str:
    return DEPARTMENTS.get(key, "frugt_og_groent")


# -- Opskrifter fra en ingrediensliste ------------------------------------
# En ingredienslinje som "500 g hakket oksekød" eller "2 fed hvidløg,
# hakket" bliver til mængde, enhed og navn. Samme regler står i app.html
# (parseLine), så egne opskrifter i browseren læses ens.
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_NUMBER = r"\d+\s+\d+\s*/\s*\d+|\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|\d*\s*[½¼¾⅓⅔]"
_LINE = re.compile(
    rf"^\s*(?:ca\.?\s*)?(?P<n>{_NUMBER})(?:\s*[-–]\s*(?P<n2>{_NUMBER}))?\s*(?P<unit>[a-zæøå]+\.?)?(?=\s|$)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
# Enhed -> (enhed i retten, faktor)
UNITS: dict[str, tuple[str, float]] = {
    "g": ("g", 1), "gr": ("g", 1), "gram": ("g", 1), "kg": ("g", 1000), "kilo": ("g", 1000),
    "dl": ("dl", 1), "l": ("dl", 10), "liter": ("dl", 10), "ml": ("dl", 0.01), "cl": ("dl", 0.1),
    "spsk": ("g", 15), "tsk": ("g", 5),
    "stk": ("stk", 1), "pk": ("stk", 1), "pakke": ("stk", 1), "pakker": ("stk", 1), "bakke": ("stk", 1),
    "bakker": ("stk", 1), "pose": ("stk", 1), "poser": ("stk", 1), "glas": ("stk", 1), "skive": ("g", 20),
    "skiver": ("g", 20), "hoved": ("stk", 1), "fed": ("fed", 1), "dåse": ("dåse", 1), "dåser": ("dåse", 1),
    "ds": ("dåse", 1), "bundt": ("bundt", 1), "bdt": ("bundt", 1),
    "knivspids": ("", 0), "nip": ("", 0), "drys": ("", 0),
}
# Vægt pr. stk, når ingrediensen ellers kun sælges efter vægt
DEFAULT_PIECE_G = 500
# Sælges i liter, så skeer regnes om til dl
LIQUIDS = {"maelk", "floede"}


def _number(text: str) -> float:
    """ "1,5", "1/2", "1 1/2", "1½" eller "½" som tal."""
    text = text.strip().replace(",", ".")
    if " " in text and "/" in text.split()[-1] and len(text.split()) == 2:
        whole, frac = text.split()
        return float(whole) + _number(frac)
    text = text.replace(" ", "")
    if text[-1] in _FRACTIONS:
        return _FRACTIONS[text[-1]] + (float(text[:-1]) if text[:-1] else 0)
    if "/" in text:
        a, b = text.split("/")
        return float(a) / float(b) if float(b) else 0
    return float(text)


def parse_line(line: str) -> tuple[float, str, str]:
    """(mængde, enhed, navn). Mængde 0 betyder efter smag."""
    line = re.sub(r"\([^)]*\)", " ", line)
    line = re.sub(r"\s+", " ", line).strip(" -•*\t")
    m = _LINE.match(line)
    if not m:
        return 0.0, "", line
    amount = _number(m["n"])
    if m["n2"]:
        amount = (amount + _number(m["n2"])) / 2
    unit, rest = (m["unit"] or "").lower().rstrip("."), m["rest"]
    if unit in UNITS:
        unit, factor = UNITS[unit]
        amount *= factor
    else:
        # Intet tal-ord som "g" eller "dl": "2 løg" er 2 stk
        rest = f"{m['unit'] or ''} {rest}".strip()
        unit = "stk"
    return (amount if unit else 0.0), unit, rest.strip(" ,.")


# Ord i linjer uden kendt ingrediens. Basisvarer regnes for at være
# derhjemme; kød og fisk bestemmer, hvilken kost retten passer til.
PANTRY_WORDS = [
    "salt", "peber", "olie", "olivenolie", "rapsolie", "mel ", "hvedemel", "sukker", "bouillon", "fond",
    "eddike", "balsamico", "sennep", "ketchup", "soja", "honning", "vand ", "krydderi", "paprika", "spidskommen",
    "karry", "oregano", "timian", "rosmarin", "kanel", "chili", "laurbær", "muskat", "gurkemeje", "ingefær",
    "garam", "tomatpuré", "tomatpure", "bagepulver", "gær ", "maizena", "majsstivelse", "vanilje", "sesam",
    "rasp", "tabasco", "worcester", "sriracha", "basilikum", "koriander", "dild", "purløg", "mynte", "estragon",
    "kardemomme", "nellike", "allehånde", "fennikelfrø", "sambal", "harissa", "pesto", "kapers", "oliven",
    "hvidvin", "rødvin", "smørelse", "fedtstof", "neutral", "fiskesauce", "fishsauce", "fiskesovs",
    "østerssauce", "hoisin", "citrongræs", "citronsaft", "limesaft", "gastrik", "stegesky", "soltørrede",
    "jalapeño", "jalapeños", "jalapenos", "nødder", "mandler", "pinjekerner", "rosiner", "tranebær", "dadler",
    "abrikoser", "kokosmel", "appelsin", "frø ", "kerner",
    "bouillonterning", "bouillonterninger", "mayonnaise", "mayo ", "flormelis", "hvidløgspulver", "løgpulver",
    "sovsekulør", "madkulør", "soya", "teriyaki", "tamari", "miso", "tahin", "sirup", "farin", "panko",
    "remoulade", "barbecuesauce", "bbq", "chutney", "citronskal", "limeskal", "isterninger", "karse",
]
PORK_WORDS = ["skinke", "bacon", "pancetta", "chorizo", "salami", "svin", "gris", "flæsk", "pølse", "prosciutto",
              "serrano", "medister", "kotelet", "spegepølse"]
FISH_WORDS = ["fisk", "laks", "torsk", "tun ", "rejer", "makrel", "sild", "ansjos", "muslinger", "hummer",
              "krabbe", "blæksprutte", "rødspætte", "kuller", "sej ", "skaldyr", "kammusling", "tang "]
MEAT_WORDS = ["kød", "okse", "kalv", "lam", "kylling", "kalkun", "and ", "andebryst", "gås", "vildt", "hjort",
              "rådyr", "kanin", "bøf", "frikadelle", "høne", "hønse", "lever", "kebab", "gyros"]
_KIND_KEYS = [
    ("fisk", ["laksefilet", "hvid_fisk", "fiskefrikadeller", "tun", "rejer"]),
    ("kylling", ["hakket_kylling", "kyllingebryst", "kyllingelaar", "hel_kylling"]),
    ("okse", ["hakket_okse", "boef", "okse_tern"]),
    ("gris", ["hakket_gris", "hakket_gris_kalv", "bacon", "stegeflaesk", "medister", "flaeskesteg", "moerbrad",
              "koteletter", "poelser", "chorizo"]),
]
_MEAT_KEYS = {k for _, keys in _KIND_KEYS for k in keys}


def _has_any(text: str, words: list[str]) -> bool:
    tokens = _tokens(text)
    return any(_has_word(tokens, w) for w in words)


def diet_flag(text: str) -> str:
    """ "pork", "fish" eller "meat", hvis linjen nævner kød eller fisk."""
    for flag, words in (("pork", PORK_WORDS), ("fish", FISH_WORDS), ("meat", MEAT_WORDS)):
        if _has_any(text, words):
            return flag
    return ""


def line_keys(name: str) -> list[str]:
    """Ingredienserne i en ingredienslinje (uden mængde)."""
    return ingredient_keys(name)


def _piece_grams(key: str) -> float:
    return NORMAL_PRICES[key][1] or DEFAULT_PIECE_G


def recipe_from_lines(
    rid: str, name: str, lines: list[str], persons: int = 4, minutes: int = 0, method: str = "", source: str = "",
) -> tuple[Recipe | None, str]:
    """En ret ud fra en ingrediensliste, eller (None, grund).

    Mængderne omregnes til 4 personer. Hovedingrediensen er den dyreste
    kendte ingrediens, med kød og fisk vægtet tre gange. Er der kød eller fisk,
    som ikke kan genkendes, kan retten ikke prissættes og bruges ikke.
    """
    scale = 4 / max(1, min(12, persons or 4))
    items: list[Item] = []
    pantry: list[str] = []
    unknown: list[str] = []
    flags: list[str] = []
    for line in lines:
        amount, unit, text = parse_line(line)
        if not text:
            continue
        keys = line_keys(text)
        if not keys:
            flag = diet_flag(text)
            staple = _has_any(text, PANTRY_WORDS)
            if flag and not staple:
                return None, f"ukendt kød eller fisk: {text}"
            if flag and flag not in flags:
                flags.append(flag)
            # Små mængder ("4 g Tex-Mex", "1 tsk røget paprika") er krydderier
            small = unit == "g" and amount <= 10
            (pantry if staple or small or not amount else unknown).append(text)
            continue
        amount *= scale
        if unit == "stk" and not NORMAL_PRICES[keys[0]][1]:
            amount, unit = amount * DEFAULT_PIECE_G, "g"
        if unit == "g" and keys[0] in LIQUIDS:  # "2 spsk mælk" er 0,3 dl, ikke 30 g
            amount, unit = amount / 100, "dl"
        if not amount:
            # "Smør til stegning" og lignende: regnes for at være derhjemme
            pantry.append(text)
            continue
        items.append(Item(round(amount, 2), unit, text[:80], keys))
    if len(items) < 2:
        return None, "for få kendte ingredienser"
    if len(unknown) > max(2, len(items) // 2):
        return None, f"for mange ukendte varer: {', '.join(unknown[:3])}"
    for i in unknown:
        items.append(Item(0, "", i[:80], []))

    def value(i: Item) -> float:
        if not i.keys:
            return 0
        grams = i.amount if i.unit == "g" else i.amount * 100 if i.unit == "dl" else i.amount * _piece_grams(i.keys[0])
        return grams * NORMAL_PRICES[i.keys[0]][0] * (3 if i.keys[0] in _MEAT_KEYS else 1)

    # Ingredienser, der koster næsten lige så meget, er også hovedingredienser
    top = max(value(i) for i in items)
    for i in items:
        i.main = value(i) >= 0.6 * top
    keys = {k for i in items for k in i.keys}
    kind = next((kind for kind, ks in _KIND_KEYS if keys & set(ks)), "vegetar")
    rid = rid or "egen-" + hashlib.sha1(name.encode()).hexdigest()[:8]
    return Recipe(rid, name.strip()[:80], kind, int(minutes or 0), items, pantry, method, source, flags), ""


# -- Opskrifter hentet fra madsider -------------------------------------
# opskrifter.json skrives af "tilbudshenter opskrifter" (se opskrifter.py)
# og indeholder kun navn, personer, tid og ingredienslisten. Retterne
# bygges her, så forbedringer af genkendelsen også gælder dem.
def load_imported(path=None) -> list[dict]:
    try:
        if path is None:
            text = resources.files("tilbudshenter.data").joinpath("opskrifter.json").read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
        return json.loads(text).get("recipes", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


@lru_cache(maxsize=1)
def imported_recipes() -> tuple[Recipe, ...]:
    result = []
    for data in load_imported():
        recipe, _ = recipe_from_lines(
            "web-" + hashlib.sha1(data["url"].encode()).hexdigest()[:10], data["name"], data["ingredients"],
            data.get("persons") or 4, data.get("minutes") or 0, "", data["url"],
        )
        if recipe:
            result.append(recipe)
    return tuple(result)


def ingredients_payload(market: dict[str, float] | None = None) -> list[dict]:
    """Ingredienserne med mønstre, så browseren kan læse egne opskrifter."""
    return [
        {"key": k, "name": name, "patterns": patterns, "exclude": exclude,
         "price": [basis_price(k, market), NORMAL_PRICES[k][1]],
         "pack": basis_pack_g(k), "veg": k in VEGETABLES, "dept": department(k), "replaces": REPLACES.get(k, [])}
        for k, (name, patterns, exclude) in INGREDIENTS.items()
    ]


def plan_payload(market: dict[str, float] | None = None) -> dict:
    """Alt, madplanen i browseren skal bruge. ``market`` er market_prices for
    tilbuddene i prishistorikken."""
    return {
        "recipes": recipes_payload(),
        "ingredients": ingredients_payload(market),
        "side": _item_payload(SIDE),
        "words": {"not_raw": _NOT_RAW, "not_raw_heading": _NOT_RAW_HEADING, "pantry": PANTRY_WORDS,
                  "pork": PORK_WORDS, "fish": FISH_WORDS, "meat": MEAT_WORDS},
        "min_veg": MIN_VEG_PER_PERSON,
        "piece_g": DEFAULT_PIECE_G,
        "units": {u: list(v) for u, v in UNITS.items()},
    }
