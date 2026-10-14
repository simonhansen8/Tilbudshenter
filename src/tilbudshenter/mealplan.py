"""Madplan ud fra ugens tilbud.

En fast samling af almindelige danske hverdagsretter, hvor hver
ingrediens kan genkendes i tilbudsaviserne. Hvert tilbud mærkes med de
ingredienser, det kan bruges som (``ingredient_keys``). Browseren vælger
så de retter, hvis hovedingrediens er på tilbud i brugerens butikker, og
viser hvilke tilbud retten kan laves af.

Retterne er til 4 personer; mængderne skaleres i browseren.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .comparison import PRODUCT_GROUPS, _has_word, _tokens

# Ingrediens -> (navn, mønstre, udelukkelser). Samme form som
# comparison.PRODUCT_GROUPS: et mønster er en liste af ord, der alle skal
# stå i varenavnet, og et ord matcher også sammensatte ord, der begynder
# eller slutter med det, medmindre det slutter med mellemrum.
INGREDIENTS: dict[str, tuple[str, list[list[str]], list[str]]] = {
    # Kød
    "hakket_okse": PRODUCT_GROUPS["hakket_okse"],
    "hakket_gris": ("hakket grisekød", [*PRODUCT_GROUPS["hakket_gris"][1], ["hakket", "svinekød"]], ["kalv", "okse"]),
    "hakket_gris_kalv": PRODUCT_GROUPS["hakket_gris_kalv"],
    "hakket_kylling": PRODUCT_GROUPS["hakket_kylling"],
    "kyllingebryst": ("kyllingebryst", [["kyllingebryst"], ["kyllingefilet"], ["kylling", "inderfilet"],
                                        ["kyllingestrimler"]], ["lage", "kalkun"]),
    "kyllingelaar": ("kyllingelår", [["kylling", "lår"], ["overlår"], ["underlår"]], ["and", "kalkun"]),
    "hel_kylling": ("hel kylling", [["hel", "kylling"], ["helkylling"], ["kylling", "hel "]], ["grill", "stegt", "lår", "bryst"]),
    "bacon": ("bacon", [["bacon"]], ["leverpostej", "kalkun", "pølse", "ost", "chips"]),
    "stegeflaesk": ("stegeflæsk", [["stegeflæsk"], ["brystflæsk"], ["flæsk", "skiver"]], ["svær", "steg"]),
    "medister": PRODUCT_GROUPS["medister"],
    "flaeskesteg": PRODUCT_GROUPS["flaeskesteg"],
    "moerbrad": PRODUCT_GROUPS["moerbrad"],
    "koteletter": ("koteletter", [["kotelet"]], ["lam", "kalv", "okse"]),
    "poelser": ("pølser", [["pølser"]], ["cocktail", "salami", "spege", "rulle", "leverpostej", "vegansk"]),
    "boef": ("bøf", [["bøf "], ["bøffer"], ["oksebøf"], ["entrecote"], ["ribeye"], ["culotte"], ["flanksteak"],
                     ["oksefilet"]], ["hakke", "burger", "kylling", "kalkun", "lam", "lammekød", "gris", "vegansk", "plantebaseret"]),
    "okse_tern": ("oksekød i tern", [["okse", "tern"], ["gullasch"], ["oksegryde"]], ["kylling", "gris"]),
    # Fisk
    "laksefilet": PRODUCT_GROUPS["laksefilet"],
    "hvid_fisk": ("torsk eller anden hvid fisk", [["torsk"], ["sej "], ["sejfilet"], ["kuller"], ["rødspætte"],
                                                  ["fiskefilet"], ["pangasius"], ["hoki"]],
                  ["fars", "rogn", "lever", "frikadelle", "tørret", "røget"]),
    "fiskefrikadeller": ("fiskefrikadeller", [["fiskefrikadelle"], ["fiskefars"]], []),
    "tun": ("tun på dåse", [["tun "], ["tunfisk"]], ["salat", "mousse"]),
    "rejer": ("rejer", [["rejer"]], ["salat", "cocktail", "chips"]),
    # Mejeri og æg
    "aeg": PRODUCT_GROUPS["aeg"],
    "maelk": ("mælk", [["letmælk"], ["minimælk"], ["sødmælk"], ["skummetmælk"]], ["kakao", "chokolade", "is "]),
    "floede": ("fløde", [["fløde "], ["piskefløde"], ["madlavningsfløde"], ["kogefløde"], ["cremefine"]],
               ["is ", "kaffe", "skum", "chokolade", "buko", "ost", "kartofler"]),
    "creme_fraiche": ("creme fraiche", [["creme", "fraiche"], ["cremefraiche"], ["fraiche"]], ["dressing"]),
    "revet_ost": ("revet ost", [["revet "], ["pizzaost"], ["mozzarella"], ["parmesan"], ["parmigiano"]],
                  ["kokos", "rødbede", "citron", "gulerod", "chokolade", "snack", "sticks", "nuggets"]),
    "feta": ("feta", [["feta"]], ["salat", "oliven"]),
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
    "majs": ("majs", [["majs "], ["majskerner"]], ["popcorn", "chips", "snack", "kolbe"]),
    # Frugt og grønt
    "kartofler": PRODUCT_GROUPS["kartofler"],
    "guleroedder": PRODUCT_GROUPS["guleroedder"],
    "loeg": ("løg", [["løg "], ["rødløg"], ["gule", "løg"]], ["ristede", "forårs", "purløg"]),
    "hvidloeg": ("hvidløg", [["hvidløg "]], ["dressing", "brød", "smør", "pølse", "gyros"]),
    "porrer": ("porrer", [["porre"]], []),
    "tomater": PRODUCT_GROUPS["tomater"],
    "agurk": PRODUCT_GROUPS["agurk"],
    "peberfrugt": PRODUCT_GROUPS["peberfrugt"],
    "broccoli": PRODUCT_GROUPS["broccoli"],
    "blomkaal": ("blomkål", [["blomkål"]], ["broccoli", "ris"]),
    "spidskaal": ("spidskål eller hvidkål", [["spidskål"], ["hvidkål"]], []),
    "roedkaal": ("rødkål", [["rødkål"]], []),
    "champignon": ("champignon", [["champignon"]], []),
    "spinat": ("spinat", [["spinat"]], ["tærte", "pandekage", "ravioli"]),
    "salat": ("salat", [["iceberg"], ["hjertesalat"], ["romaine"], ["salathoved"], ["rucola"]], ["dressing"]),
    "groenne_boenner": ("grønne bønner", [["grønne", "bønner"], ["haricots"], ["bønner", "haricot"]], []),
    "aerter": ("ærter", [["ærter "]], ["snack", "wasabi"]),
    "squash": ("squash", [["squash"]], ["saft", "sodavand", "drik", "læske", "cl ", "tuborg", "faxe"]),
    "wokgroent": ("wokgrøntsager", [["wokgrønt"], ["wokblanding"]], []),
    "citron": ("citron", [["citroner"], ["citron "]], ["saft", "juice", "te ", "vand", "kage", "is "]),
    "persille": ("persille", [["persille"]], ["pesto", "smør"]),
    "aebler": PRODUCT_GROUPS["aebler"],
}

# Anslået normalpris (kr pr. kg eller liter) og vægt pr. stk, dåse, fed
# eller bundt i gram. Bruges til rettens pris, når en vare ikke er på
# tilbud, og til at omregne mellem stk og kg.
NORMAL_PRICES: dict[str, tuple[float, float]] = {
    "hakket_okse": (100, 0), "hakket_gris": (65, 0), "hakket_gris_kalv": (75, 0), "hakket_kylling": (90, 0),
    "kyllingebryst": (110, 0), "kyllingelaar": (45, 0), "hel_kylling": (50, 1400), "bacon": (120, 0),
    "stegeflaesk": (80, 0), "medister": (70, 0), "flaeskesteg": (70, 0), "moerbrad": (120, 0),
    "koteletter": (70, 200), "poelser": (90, 60), "boef": (250, 150), "okse_tern": (150, 0),
    "laksefilet": (200, 125), "hvid_fisk": (160, 125), "fiskefrikadeller": (100, 60), "tun": (100, 185),
    "rejer": (150, 0),
    "aeg": (50, 60), "maelk": (12, 0), "floede": (45, 0), "creme_fraiche": (40, 0), "revet_ost": (90, 0),
    "feta": (100, 0), "smoer": (100, 0),
    "pasta": (20, 0), "lasagneplader": (40, 0), "ris": (25, 0), "nudler": (40, 0), "tortilla": (60, 40),
    "burgerboller": (50, 70), "poelsebroed": (40, 40), "pizzadej": (30, 400), "hakkede_tomater": (15, 400),
    "kidneyboenner": (20, 400), "kokosmaelk": (40, 400), "majs": (30, 300),
    "kartofler": (12, 0), "guleroedder": (10, 80), "loeg": (12, 150), "hvidloeg": (80, 5), "porrer": (25, 250),
    "tomater": (30, 100), "agurk": (30, 400), "peberfrugt": (40, 200), "broccoli": (30, 400),
    "blomkaal": (25, 800), "spidskaal": (15, 1000), "roedkaal": (25, 500), "champignon": (50, 0),
    "spinat": (60, 0), "salat": (30, 400), "groenne_boenner": (30, 0), "aerter": (25, 0), "squash": (25, 300),
    "wokgroent": (30, 0), "citron": (30, 100), "persille": (100, 30), "aebler": (20, 150),
}

# Ord der betyder, at tilbuddet ikke er en råvare
_NOT_RAW = [
    "færdigret", "pålæg", "suppe", "sauce", "dressing", "chips", "snack", "juice", "spyd", "kebab",
    "gratin", "fyld", "smoothie", "grillet", "salatbar", "ravioli",
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
        I(2, "stk", "romainesalat", "salat"),
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
        for key in candidates:
            if key not in found and _matches(tokens, INGREDIENTS[key]):
                found.append(key)
    return tuple(found)


def _amount(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def recipes_payload() -> list[dict]:
    """Retterne som siden og appen bruger dem."""
    return [
        {
            "id": r.id,
            "name": r.name,
            "kind": r.kind,
            "minutes": r.minutes,
            "items": [
                {
                    "amount": _amount(i.amount), "unit": i.unit, "name": i.name, "keys": i.keys, "main": i.main,
                    # Normalpris pr. kg og vægt pr. stk for den første ingrediens
                    "price_kg": NORMAL_PRICES[i.keys[0]][0], "piece_g": NORMAL_PRICES[i.keys[0]][1],
                }
                for i in r.items
            ],
            "pantry": r.pantry,
            "method": r.method,
        }
        for r in RECIPES
    ]
