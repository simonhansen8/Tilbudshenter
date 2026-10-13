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
            "kiks", "småkager", "julekager", "marabou", "haribo", "toms", "pringles",
            "nødder", "nøddemix", "peanuts", "mandler", "flødeboller", "karamel",
            "is ", "isvafler", "isbæger", "iskasse", "isbar", "isdessert", "kage",
            "snack", "nougat", "trøfler", "trøffel", "marshmallows", "mallows",
            "skumfidus", "tyggegummi", "dumle", "smarties", "maltesers",
            "snickers", "werthers", "toffifee", "mentos", "quality street",
            "ferrero", "lindt", "milka", "ritter sport", "fazer", "cloetta",
            "juleskum", "katjes", "sallos", "taffel", "cornitas", "bugles",
            "vafler", "brownie", "brownies", "tiramisu", "danette", "dessert",
            "desserter", "magnum", "solero", "frisko", "sun lolly", "jerry",
            "macarons", "profiteroles", "digestive", "cookies", "cookie",
            "biscuits", "dan cake", "citronmåne", "slikpose",
        ],
    },
    "drikkevarer": {
        "navn": "Drikkevarer",
        "noegleord": [
            "sodavand", "cola", "coca cola", "fanta", "squash", "pepsi", "faxe kondi", "juice", "saft",
            "vand ", "kildevand", "danskvand", "energidrik", "smoothie", "iste",
            "powerade", "monster energy", "red bull", "drik", "rynkeby",
            "ribena", "solbærdrik", "cocio", "kakaomælk",
        ],
    },
    "oel_og_vin": {
        "navn": "Øl, vin & spiritus",
        "noegleord": [
            "øl", "ølmarked", "pilsner", "tuborg", "carlsberg", "ipa", "rødvin",
            "hvidvin", "rosé", "vin ", "vine", "cava", "prosecco", "champagne",
            "spiritus", "vodka", "gin ", "whisky", "rom ", "cider", "bag in box",
            "appassimento", "ripasso", "valpolicella", "rioja", "bordeaux",
            "bourgogne", "chablis", "chablisienne", "côtes", "cotes", "rhône",
            "rhone", "pinot", "grigio", "sauvignon", "chardonnay", "merlot",
            "zin ", "tawny", "portvin", "colheita", "reserva", "riesling",
            "grüner veltliner", "shots", "likør",
        ],
    },
    "kaffe_og_te": {
        "navn": "Kaffe & te",
        "noegleord": [
            "kaffe", "espresso", "kaffebønner", "kapsler", "te ", "tebreve",
            "gevalia", "lavazza", "helbønner", "l or", "chai", "latte", "nescafé", "nescafe",
        ],
    },
    "koed": {
        "navn": "Kød & fjerkræ",
        "noegleord": [
            "oksekød", "kylling", "kalkun", "svinekød", "flæsk",
            "bacon", "mørbrad", "koteletter", "skinke", "medister", "pølser",
            "pølse", "bøf", "bøffer", "steak", "steaks", "steg", "okse",
            "culotte", "entrecote", "entrecoté", "ribeye", "rib eye", "rib eyes",
            "kalv", "lam ", "lammekød", "lammekølle", "and ", "andebryst",
            "andelår", "pekingand", "berberiand", "andemenu", "fasan", "krondyr",
            "hjorte", "vildsvin", "frikadeller", "kyllingebryst", "kyllingelår",
            "nakkekoteletter", "nakkefilet", "ribbensteg", "spareribs",
            "kødpålæg", "leverpostej", "postej", "rullepølse", "salami",
            "pålæg", "kebab", "kød", "chorizo", "serrano", "bresaola",
            "kabanossi", "pancetta", "salchichón", "roastbeef", "gullasch",
            "stroganoff", "schnitzel", "cordon bleu", "porchetta",
            "hamburgerryg", "nuggets", "wings", "fars", "gyros", "højreb",
            "højrebsfilet", "tykstegsbøffer", "mørbradbøffer",
        ],
    },
    "fisk": {
        "navn": "Fisk & skaldyr",
        "noegleord": [
            "laks", "torsk", "fisk", "rejer", "tun ", "tunfisk", "makrel", "sild",
            "rødspætte", "kuller", "sej ", "fiskefrikadeller", "muslinger",
            "skaldyr", "hummer", "fiskefilet", "fiskefileter", "rogn", "sushi",
            "fiskefars", "fiskepinde", "tigerrejer",
        ],
    },
    "mejeri": {
        "navn": "Mejeri & æg",
        "noegleord": [
            "mælk", "letmælk", "minimælk", "sødmælk", "yoghurt", "skyr",
            "ost", "smør", "fløde", "creme fraiche", "cremefraiche", "kærnemælk",
            "æg", "lurpak", "arla", "kvark", "hytteost", "piskefløde",
            "mozzarella", "feta", "parmesan", "riberhus", "smørbar", "danbo",
            "havarti", "gouda", "tilsiter", "emmentaler", "cheddar", "samsø",
            "grana padano", "brie", "camembert", "castello", "philadelphia",
            "mascarpone", "burrata", "danonino", "dronning dagmar", "margarine",
            "den leende ko", "fromage", "revet",
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
            "grøntsager", "grøntsag", "mango", "ananas", "kiwi", "klementiner",
            "clementiner", "mandariner", "rødbeder", "hvidløg", "ingefær",
            "krydderurter", "græskar", "lime", "blommer", "bimi", "basilikum",
            "chili", "kastanjer", "majs", "ærter", "wokmix", "rosiner",
        ],
    },
    "broed_og_bager": {
        "navn": "Brød & bageri",
        "noegleord": [
            "brød", "rugbrød", "franskbrød", "boller", "bolle", "rundstykker",
            "toastbrød", "wienerbrød", "croissant", "bagel", "tortilla",
            "pitabrød", "knækbrød", "flutes", "baguette", "snegl", "snegle",
            "tebirkes", "gifflar", "pain au chocolat", "speltstykker",
            "skagenslapper", "morgenkager", "wienerpekan", "spandauer",
            "valnøddestykke", "muffins", "sandwich", "tarteletter", "dej",
            "pinsa", "bagerens",
        ],
    },
    "frost": {
        "navn": "Frost",
        "noegleord": [
            "frost", "frossen", "frosne", "dybfrost", "pizza", "pommes frites",
            "isbåde", "forårsruller", "kartoffelbåde", "røsti",
            "kartoffelrøsti", "kartoffelgratin",
        ],
    },
    "kolonial": {
        "navn": "Kolonial",
        "noegleord": [
            "pasta", "spaghetti", "ris ", "jasminris", "basmatiris", "risengrød",
            "mel", "sukker", "havregryn", "gryn", "müsli", "mysli", "cornflakes",
            "flakes", "havrefras", "morgenmad", "konserves", "flåede tomater",
            "bønner", "linser", "olie", "olivenolie", "eddike", "ketchup",
            "mayonnaise", "sennep", "krydderi", "bouillon", "sauce", "pesto",
            "honning", "marmelade", "syltetøj", "gelé", "nutella",
            "peanutbutter", "nudler", "lasagne", "lasagneplader", "fusilli",
            "penne", "farfalle", "gnocchi", "fettuccine", "suppehorn", "suppe",
            "dinner kit", "færdigret", "marcipan", "vaniljestænger",
            "kanelstænger", "kanelstang", "stjerneanis", "nelliker", "bageingredienser",
            "fondant", "glasur", "kakao", "dressing", "survarer", "tyttebær",
            "bulgur", "couscous", "quinoa", "tacos", "tex mex",
        ],
    },
    "husholdning": {
        "navn": "Husholdning",
        "noegleord": [
            "vaskemiddel", "vaskepulver", "opvask", "toiletpapir", "papir",
            "køkkenrulle", "rengøring", "skyllemiddel", "affaldsposer",
            "opvasketabs", "neutral", "ajax", "fairy", "vim", "stearinlys",
            "fyrfadslys", "kronelys", "bloklys", "duftlys", "batterier",
            "domestos", "bref", "harpic", "vel ", "toiletrens", "kleenex",
            "lommetørklæder", "servietter", "skumklude", "klude",
        ],
    },
    "personlig_pleje": {
        "navn": "Personlig pleje",
        "noegleord": [
            "shampoo", "balsam", "tandpasta", "tandbørste", "deodorant", "deo ",
            "sæbe", "showergel", "shower", "creme", "barberblade", "bind",
            "tamponer", "tampax", "always", "tena", "hudpleje", "makeup",
            "make up", "mundpleje", "zendium", "colgate", "serum", "ansigtsrens",
            "mascara", "parfume", "hårpleje", "hair", "gillette", "trimmer",
            "nicotinell", "quickmist", "nikotin", "livol", "vitaminer",
            "brusetabletter", "omega", "kreatin", "whey", "proteinpulver",
            "gummies", "negle", "vipper",
        ],
    },
    "baby": {
        "navn": "Baby",
        "noegleord": ["bleer", "babymad", "vådservietter", "libero", "pampers", "modermælk"],
    },
    "dyr": {
        "navn": "Kæledyr",
        "noegleord": [
            "hundemad", "kattemad", "kattegrus", "dyrefoder", "whiskas", "pedigree",
            "hund ", "hunde", "kat ", "katte", "halsbånd", "reflekssnor", "tyggeruller",
        ],
    },
    "nonfood": {
        "navn": "Non-food",
        "noegleord": [
            "tv ", "fjernsyn", "telefon", "tøj ", "sko ", "legetøj", "værktøj",
            "møbler", "dyne", "pude", "sengetøj", "håndklæder", "gryde",
            "pande", "støvsuger", "kaffemaskine", "airfryer", "blomster",
            "potteplante", "cykel", "jakke", "bukser", "trøje",
            "silvercrest", "parkside", "livarno", "prosonic", "skelet",
            "samsung", "apple", "iphone", "ipad", "airpods", "galaxy",
            "hisense", "denver", "printer", "højttaler", "soundbar",
            "høretelefoner", "radio", "køleskab", "fryseskab", "ovn",
            "komfur", "kogeplade", "emhætte", "vaskemaskine", "blender",
            "foodprocessor", "køkkenmaskine", "elkedel", "vaffeljern", "kniv",
            "knive", "bestik", "skålesæt", "bageform", "silikoneform",
            "bagestål", "bagespade", "afkølingsrist", "dejskraber", "kurv",
            "kurve", "tæppe", "sengesæt", "lagen", "puf", "madras", "seng",
            "strømper", "tights", "støvler", "sneakers", "hjemmesko", "jeans",
            "bluse", "shirt", "sweatshirt", "skjorte", "kjole", "nederdel",
            "top ", "vest ", "frakke", "strik", "pyjamas", "fleece",
            "handsker", "luffer", "hue ", "tørklæde", "trusser", "boxershorts",
            "lingeri", "flyverdragt", "undertøj", "garn", "bånd", "maske",
            "masker", "pynt", "dekoration", "lyskæde", "lampe", "roser",
            "lyng", "krysantemum", "orkidé", "lilje", "kalanchoe", "sukkulent",
            "cypres", "nordmannsgran", "bjergfyr", "plante", "blomst",
            "brændende kærlighed", "pottejord", "spil", "puslespil", "lego",
            "pokémon", "bog", "bøger", "legekøkken", "dukkehus", "legemad",
            "squishy", "byggeklodser", "skruetrækker", "hammer", "økse",
            "sav", "skruemaskine", "hæftepistol", "hultang", "forlængerledning",
            "termometer", "køkkenvægt", "kuffert", "rygsæk", "taske",
            "mulepose", "madkasse", "drikkedunk", "krus", "opbevaring",
            "stickers", "gasgrill", "skammel", "kødhakker", "stol", "bord", "romaskine", "dørmåtte", "duge",
            "wi fi", "kostume", "julekalenderbog",
        ],
    },
}

FOOD_CATEGORIES = {
    "koed", "fisk", "mejeri", "frugt_og_groent", "broed_og_bager", "frost",
    "kolonial", "slik_og_snacks", "drikkevarer", "kaffe_og_te",
}


# Bøjningsendelser, så "croissant" også matcher "smørcroissanter"
_ENDINGS = ("e", "r", "er", "en", "et", "ne", "erne")

# Ord der indleder en tilføjelse: "Laks med spinat" er laks, ikke spinat
_QUALIFIERS = re.compile(r"\s(?:med|i|til|uden|på|og tilbehør)\s", re.IGNORECASE)


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
    Nøgleord på to bogstaver ("æg") matcher kun hele ord og ordslutninger
    ("skrabeæg").
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
                whole_only = word.endswith(" ") or len(tokens) > 1 or len(tokens[0]) < 2
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
                    elif token.endswith(word) or (
                        len(word) >= 3 and any(token.endswith(word + e) for e in _ENDINGS)
                    ):
                        q = len(word) + 2
                    elif len(word) >= 3 and token.startswith(word):
                        q = len(word)
                    else:
                        continue
                    quality = max(quality, q)
            if quality > best_quality:
                best_key, best_quality = key, quality
        return best_key

    def categorize(self, heading: str, description: str = "") -> str:
        # Overskriften vægter højest, og først det, der står før "med", "i" osv.
        main = _QUALIFIERS.split(heading, maxsplit=1)[0]
        return (
            self._best_match(main)
            or self._best_match(heading)
            or self._best_match(description)
            or UNCATEGORIZED
        )

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
