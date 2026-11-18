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
from urllib.parse import urlparse

from .comparison import PER_PIECE_GROUPS, PRODUCT_GROUPS, _has_word, _tokens, product_group

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
                                                        ["hakket", "svin", "kalv"], ["hakket", "kalv", "flæsk"]],
                         PRODUCT_GROUPS["hakket_gris_kalv"][2]),
    "hakket_kylling": PRODUCT_GROUPS["hakket_kylling"],
    "kyllingebryst": ("kyllingebryst", [["kyllingebryst"], ["kyllingefilet"], ["kylling", "inderfilet"],
                                        ["kyllingeinderfilet"], ["kyllingestrimler"]], ["lage", "kalkun"]),
    "kyllingelaar": ("kyllingelår", [["kylling", "lår"], ["overlår"], ["underlår"], ["kyllingelårfilet"], ["kylling", "lårfilet"]], ["and", "kalkun"]),
    "hel_kylling": ("hel kylling", [["hel", "kylling"], ["helkylling"], ["kylling", "hel "], ["kylling "], ["kyllinger "]],
                    ["grill", "stegt", "lår", "bryst", "filet", "hakket", "pålæg", "kogt", "wings", "tern", "pose", "posen"]),
    "bacon": ("bacon", [["bacon"], ["guanciale"]], ["leverpostej", "kalkun", "pølse", "ost", "chips"]),
    "stegeflaesk": ("stegeflæsk", [["stegeflæsk"], ["brystflæsk"], ["flæsk", "skiver"]], ["svær", "steg"]),
    "medister": PRODUCT_GROUPS["medister"],
    "flaeskesteg": PRODUCT_GROUPS["flaeskesteg"],
    "moerbrad": ("mørbrad af gris", [*PRODUCT_GROUPS["moerbrad"][1], ["svinemørbrad"], ["mørbrader"]],
                 PRODUCT_GROUPS["moerbrad"][2]),
    # "kotelet" alene finder ikke nakke- og svinekoteletter, der slutter på "koteletter"
    "koteletter": ("koteletter", [["kotelet"], ["koteletter"]], ["lam", "kalv", "okse"]),
    "ribben": ("ribben eller spareribs", [["ribben"], ["spareribs"], ["ribbensteg"], ["svine", "ribs"]],
               ["pålæg", "kalv", "okse", "lam"]),
    "svinekam": ("svinekam eller nakkefilet", [["svinekam"], ["grisekam"], ["kamfilet"], ["kamsteg"], ["nakkefilet"],
                                               ["kam", "gris"]], ["kotelet", "koteletter", "pålæg", "røget", "hamburgerryg"]),
    "skinkekoed": ("skinkeschnitzler, -strimler eller -tern",
                   [["skinkeschnitzel"], ["skinkeschnitzler"], ["skinkestrimler"], ["skinketern"], ["skinkekød"],
                    ["skinke", "strimler"], ["skinke", "tern"], ["skinke", "schnitzel"]],
                   ["paneret", "panerede", "pandeklar", "ost", "pålæg"]),
    "lufttoerret_skinke": ("parma- eller serranoskinke", [["parmaskinke"], ["serranoskinke"], ["serrano "], ["prosciutto"],
                                                           ["lufttørret", "skinke"], ["spegeskinke"]],
                           ["ost", "pizza", "chips"]),
    "poelser": ("pølser", [["pølser"], ["frankfurter"], ["wienerpølse"], ["salsiccia"]], ["cocktail", "salami", "spege", "rulle", "leverpostej", "vegansk"]),
    "chorizo": ("chorizo", [["chorizo"]], ["chips", "snack", "pizza", "skiver"]),
    "boef": ("bøf", [["bøf "], ["bøffer"], ["oksebøf"], ["entrecote"], ["ribeye"], ["culotte"], ["flanksteak"], ["flatsteak"],
                     ["oksefilet"], ["tykstegsbøf"], ["rumpsteak"], ["rump", "steak"], ["okse", "steak"], ["steak"], ["tournedos"], ["picanha"],
                     ["entrecôte"], ["sirloin"], ["cuvette"]],
             ["hakke", "burger", "kylling", "kalkun", "lam", "lammekød", "gris", "svin", "vegansk", "plantebaseret",
              "laks", "fisk", "tun", "veggie", "vegetar", "grønt", "grønsag", "sauce", "krydderi", "house", "pommes",
              "fritter", "kartof", "frites", "sandwich", "bacon"]),
    "okse_tern": ("oksekød i tern", [["okse", "tern"], ["gullasch"], ["gulasch"], ["oksegryde"], ["oksekødsstrimler"], ["oksestrimler"],
                                     ["okse", "strimler"]],
                  ["kylling", "gris"]),
    "oksesteg": ("oksesteg (tyndsteg, inderlår, klump, tykkam eller bov)",
                 [["oksesteg"], ["tyndsteg"], ["roastbeef"], ["okseinderlår"], ["okse", "inderlår"], ["okseklump"],
                  ["oksetykkam"], ["tykkam", "okse"], ["oksebov"], ["bov", "okse"], ["oksehøjreb"], ["højreb"],
                  ["oksespidsbryst"], ["okseyderlår"]],
                 ["pålæg", "hakket", "kalv", "gris", "bouillon", "fond"]),
    "oksemoerbrad": ("oksemørbrad", [["oksemørbrad"], ["mørbrad", "okse"]], ["pålæg", "kalv", "gris"]),
    "kalvekoed": ("kalvekød", [["kalvekød"], ["kalveculotte"], ["kalvemørbrad"], ["kalveschnitzel"], ["kalveschnitzler"],
                               ["kalvestrimler"], ["kalvetykkam"], ["kalvebov"], ["kalvesteg"], ["kalvegrydesteg"],
                               ["kalvefilet"], ["kalvecuvette"], ["kalveinderlår"], ["kalvesmåkød"], ["kalv", "tern"]],
                  ["hakket", "gris", "grise", "svin", "svine", "sticks", "spareribs", "lever", "pølse", "fond", "bouillon", "paneret",
                   "pålæg"]),
    "lam": ("lammekød", [["lammekølle"], ["lammekød"], ["lammeculotte"], ["lammefilet"], ["lammekotelet"],
                         ["lammekoteletter"], ["lammebov"], ["lammesteak"], ["lammekam"], ["lammekrone"],
                         ["lammemørbrad"], ["lam "]],
            ["skind", "fjord", "fjordens", "uld", "pølse"]),
    "kalkun": ("kalkun", [["kalkunbryst"], ["kalkunfilet"], ["kalkunstrimler"], ["kalkun", "strimler"],
                          ["kalkunschnitzel"], ["kalkunschnitzler"], ["kalkun", "schnitzel"], ["kalkunoverlår"],
                          ["kalkununderlår"], ["kalkunkød"], ["hakket", "kalkun"]],
               ["paneret", "nuggets", "bacon", "pålæg", "cordon", "hakkebøf", "hakkebøffer", "røget", "middagskalkun"]),
    "and": ("and", [["andebryst"], ["andebryster"], ["andelår"], ["and ", "hel "], ["landand"], ["andesteg"],
                    ["juleand"], ["andestege"]],
            ["confiteret", "confiterede", "menu", "andemenu", "sauce", "dyne", "stegt"]),
    # Fisk
    "laksefilet": ("laksefilet", [*PRODUCT_GROUPS["laksefilet"][1], ["laks "], ["lakseside"], ["laksesider"],
                                  ["ørred"], ["ørredfilet"]],
                   # "Fintskåret laks" er røget laks i skiver, og laks på dåse er ikke en laksefilet
                   [*PRODUCT_GROUPS["laksefilet"][2], "skiver", "fintskåret", "fintskåren", "dåse", "dåser"]),
    # Kold- og varmrøget laks og gravad laks; laksefilet udelukker dem
    "roeget_laks": ("røget laks", [["røget", "laks"], ["gravad", "laks"], ["røgede", "laks"]],
                    ["paté", "pate", "salat", "topping", "mousse", "sandwich", "røræg", "smørrebrød"]),
    "hvid_fisk": ("torsk eller anden hvid fisk", [["torsk"], ["sej "], ["sejfilet"], ["kuller"], ["rødspætte"],
                                                  ["fiskefilet"], ["pangasius"], ["hoki"],
                                                  ["lyssej"], ["mørksej"], ["kulmule"], ["hellefisk"], ["rødfisk"],
                                                  ["havkat"], ["rødtunge"], ["skrubbe "], ["skrubbefilet"],
                                                  ["aborre"], ["helleflynder"], ["ising"], ["multe"], ["knurhane"],
                                                  ["hvilling"], ["brosme"], ["søtunge"], ["tilapia"]],
                  ["fars", "rogn", "lever", "frikadelle", "tørret", "røget"]),
    "fiskefrikadeller": ("fiskefrikadeller", [["fiskefrikadelle"], ["fiskefars"]], []),
    "tun": ("tun på dåse", [["tun "], ["tunfisk"]], ["salat", "mousse"]),
    "rejer": ("rejer", [["rejer"]], ["salat", "cocktail", "chips"]),
    # Mejeri og æg
    # Æggeblommer og -hvider købes som æg
    "aeg": ("æg", [*PRODUCT_GROUPS["aeg"][1], ["æggeblomme"], ["æggeblommer"], ["æggehvide"], ["æggehvider"]],
            PRODUCT_GROUPS["aeg"][2]),
    "maelk": ("mælk", [["letmælk"], ["minimælk"], ["sødmælk"], ["skummetmælk"], ["kærnemælk"], ["mælk "]],
              ["kakao", "chokolade", "is "]),
    "floede": ("fløde", [["fløde "], ["piskefløde"], ["madlavningsfløde"], ["kogefløde"], ["cremefine"]],
               ["is ", "kaffe", "skum", "chokolade", "buko", "ost", "kartofler"]),
    "creme_fraiche": ("creme fraiche", [["creme", "fraiche"], ["cremefraiche"], ["fraiche"]], ["dressing"]),
    # "revet" alene er ikke ost: "revet ingefær", "hvidkål - revet"
    "revet_ost": ("revet ost", [["revet", "ost"], ["revet", "topping"], ["pizzaost"], ["gratinost"],
                                ["mozzarella"], ["mozarella"], ["cheddar"],
                                *[["revet", w] for w in ["gouda", "emmentaler", "havarti", "gruyère", "gruyere",
                                                          "comté", "comte", "danbo"]]],
                  ["kokos", "rødbede", "citron", "gulerod", "chokolade", "snack", "sticks", "nuggets", "skiver",
                   "twist", "kiks"]),
    # Frisk mozzarella i kugler er en anden vare end revet mozzarella
    "frisk_mozzarella": ("frisk mozzarella", [*[[w, "frisk"] for w in ["mozzarella", "mozarella"]],
                                              *[[w, "kugle"] for w in ["mozzarella", "mozarella"]],
                                              ["bufala"], ["buffel"], ["burrata"]],
                         ["revet", "snack", "sticks", "pizza "]),
    # Parmesan er dyrere end revet ost og kan ikke erstattes af pizzatopping
    "parmesan": ("parmesan", [["parmesan"], ["parmigiano"], ["grana", "padano"], ["pecorino"]],
                 ["chips", "snack", "kiks", "chili"]),
    "feta": ("feta", [["feta"], ["salatost"]], ["salat ", "oliven"]),
    "yoghurt": ("yoghurt eller skyr", [["yoghurt"], ["skyr"]],
                ["drik", "drikke", "is ", "müsli", "musli", "bar", "smoothie", "dressing", "frugt", "vanilje",
                 "soja", "havre", "plante", "vegansk"]),
    "smoer": PRODUCT_GROUPS["smoer"],
    # Kolonial og brød
    "pasta": ("pasta", [["pasta "], ["spaghetti"], ["penne"], ["fusilli"], ["makaroni"], ["tagliatelle"],
                        ["farfalle"], ["rigatoni"], ["pastaskruer"],
                        ["orzo"], ["linguine"], ["fettuccine"], ["pappardelle"], ["spaghettini"], ["tortiglioni"],
                        ["conchiglie"], ["orecchiette"], ["bucatini"], ["macaroni"]],
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
    "kokosmaelk": ("kokosmælk", [["kokosmælk"], ["kokosfløde"]], ["drik"]),
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
    "tomater": ("tomater", [*PRODUCT_GROUPS["tomater"][1], ["tomat "], ["bøftomat"]],
                [*PRODUCT_GROUPS["tomater"][2], "ketchup", "juice", "saft"]),
    "cherrytomater": ("cherrytomater", [["cherrytomat"], ["snacktomat"], ["cherry", "tomater"]], ["soltørrede", "dåse"]),
    "agurk": PRODUCT_GROUPS["agurk"],
    "peberfrugt": PRODUCT_GROUPS["peberfrugt"],
    "broccoli": PRODUCT_GROUPS["broccoli"],
    "blomkaal": ("blomkål", [["blomkål"]], ["broccoli", "ris"]),
    "spidskaal": ("spidskål eller hvidkål", [["spidskål"], ["hvidkål"], ["savoykål"], ["glaskål"]], []),
    "roedkaal": ("rødkål", [["rødkål"]], []),
    "champignon": ("champignon", [["champignon"], ["portobello"], ["østershat"], ["shiitake"]], []),
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
    # Æblesaft, -most og -eddike er ikke æbler
    "aebler": (PRODUCT_GROUPS["aebler"][0], PRODUCT_GROUPS["aebler"][1],
               [*PRODUCT_GROUPS["aebler"][2], "saft", "juice", "most", "cider", "eddike", "mos", "chips", "kage"]),
    # Flere grøntsager, bælgfrugter, mejerivarer og tilbehør, som opskrifterne
    # ofte bruger
    "skalotteloeg": ("skalotteløg", [["skalotteløg"], ["skalotter"], ["skalotte"], ["echalion"]], ["ristede", "syltede"]),
    "aubergine": ("aubergine", [["aubergine"], ["auberginer"]], ["dip", "creme", "grillet", "grillede"]),
    "soede_kartofler": ("søde kartofler", [["sød", "kartof"], ["søde", "kartof"], ["sødkartof"]],
                        ["fritter", "chips", "pommes", "mos", "frites"]),
    "pak_choi": ("pak choi", [["pak", "choi"], ["pakchoi"], ["pak", "choy"], ["bok", "choy"]], []),
    # Aspargeskartofler er kartofler, og aspargessnitter og tarteletter er på dåse
    "asparges": ("asparges", [["asparges"]], ["suppe", "chips", "kartofler", "kartoffel", "snitter", "tarteletter", "dåse"]),
    "pastinak": ("pastinak eller persillerod", [["pastinak"], ["persillerod"], ["persillerødder"]], ["chips"]),
    "butternut": ("butternut eller græskar", [["butternut"], ["græskar"], ["hokkaido"]],
                  ["kerner", "frø", "seeds", "suppe", "olie", "kage", "is "]),
    "fennikel": ("fennikel", [["fennikel"]], ["frø", "te ", "pølse"]),
    "knoldselleri": ("knoldselleri", [["knoldselleri"], ["selleri", "knold"], ["sellerirod"]], ["salt", "chips"]),
    "groenkaal": ("grønkål", [["grønkål"], ["sortkål"], ["cavolo"]], ["chips", "snack"]),
    "rosenkaal": ("rosenkål", [["rosenkål"]], []),
    "radiser": ("radiser", [["radise"], ["radiser"]], []),
    "roedbeder": ("rødbeder", [["rødbede"]], ["chips", "juice", "saft", "salat"]),
    "boennespirer": ("bønnespirer", [["bønnespirer"], ["beansprouts"]], []),
    "sukkeraerter": ("sukkerærter", [["sukkerærter"], ["mangetout"], ["sugar", "snap"]], []),
    "kikaerter": ("kikærter", [["kikærter"], ["kikært"]], ["chips", "snack", "mel ", "hummus", "pasta"]),
    "hvide_boenner": ("hvide bønner", [["cannellini"], ["smørbønner"], ["hvide", "bønner"], ["borlotti"],
                                       ["butterbønner"]], ["tomatsauce", "tomat", "kaffe", "grønne"]),
    "tofu": ("tofu", [["tofu"]], []),
    "ricotta": ("ricotta", [["ricotta"]], []),
    "mascarpone": ("mascarpone", [["mascarpone"]], []),
    "flodeost": ("flødeost", [["flødeost"], ["philadelphia"], ["smøreost"]], ["laks", "kage", "rejer"]),
    "hytteost": ("hytteost", [["hytteost"]], []),
    "halloumi": ("halloumi eller grillost", [["halloumi"], ["grillost"], ["paneer"]], []),
    "gedeost": ("gedeost", [["gedeost"], ["chèvre"], ["chevre"]], []),
    "couscous": ("couscous", [["couscous"]], ["salat"]),
    "bulgur": ("bulgur", [["bulgur"]], ["salat"]),
    "quinoa": ("quinoa", [["quinoa"]], ["salat", "chips"]),
    "perlebyg": ("perlebyg", [["perlebyg"], ["pearl", "barley"], ["bygkerner"], ["perlespelt"]], []),
    "gnocchi": ("gnocchi", [["gnocchi"]], []),
    "butterdej": ("butterdej eller tærtedej", [["butterdej"], ["filodej"], ["tærtedej"], ["filo "]], []),
    "pitabroed": ("pitabrød eller naan", [["pitabrød"], ["pita "], ["naan"], ["naanbrød"]], ["chips", "snack"]),
    "broed": ("brød", [["brød "], ["baguette"], ["baguettes"], ["flute "], ["flutes"], ["ciabatta"], ["focaccia"],
                       ["franskbrød"], ["landbrød"], ["surdejsbrød"], ["hvedebrød"], ["toastbrød"], ["rugbrød"]],
              ["rasp", "krummer", "crumbs", "crouton", "croutoner", "chips", "kage", "smørrebrød", "pålæg", "hvidløgsbrød",
               "hvedemel", "mel ", "flour"]),
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
    "moerbrad": (110, 500), "koteletter": (85, 200), "ribben": (55, 1000), "poelser": (90, 60), "boef": (280, 150), "okse_tern": (180, 500),
    "svinekam": (90, 1000), "skinkekoed": (100, 400), "lufttoerret_skinke": (350, 80), "oksesteg": (200, 1000),
    "oksemoerbrad": (450, 600), "kalvekoed": (220, 500), "lam": (180, 1000), "kalkun": (120, 500), "and": (180, 350),
    "laksefilet": (230, 125), "roeget_laks": (300, 150), "hvid_fisk": (200, 125), "fiskefrikadeller": (120, 60), "tun": (120, 185),
    "rejer": (220, 400),
    "aeg": (55, 60), "maelk": (14, 1000), "floede": (50, 250), "creme_fraiche": (45, 200), "revet_ost": (110, 175),
    "frisk_mozzarella": (110, 125),
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
    "skalotteloeg": (40, 30), "aubergine": (35, 300), "soede_kartofler": (25, 300), "pak_choi": (60, 200),
    "asparges": (90, 250), "pastinak": (25, 150), "butternut": (20, 1200), "fennikel": (40, 300),
    "knoldselleri": (20, 700), "groenkaal": (50, 250), "rosenkaal": (40, 500), "radiser": (40, 150),
    "roedbeder": (15, 150), "boennespirer": (40, 200), "sukkeraerter": (80, 150), "kikaerter": (25, 400),
    "hvide_boenner": (25, 400), "tofu": (50, 300), "ricotta": (70, 250), "mascarpone": (80, 250),
    "flodeost": (80, 200), "hytteost": (45, 250), "halloumi": (120, 200), "gedeost": (160, 150),
    "couscous": (30, 500), "bulgur": (30, 500), "quinoa": (60, 400), "perlebyg": (25, 500), "gnocchi": (35, 500),
    "butterdej": (60, 275), "pitabroed": (50, 80), "broed": (35, 400),
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


def basis_price(key: str, market: dict[str, float] | None = None, shelf: dict[str, dict] | None = None) -> float:
    """Basisprisen i kr pr. kg: den rigtige hyldepris fra en webshop, når den
    kendes (``shelf`` er shelf.basis_prices), ellers den anslåede pris, hævet
    til det typiske tilbud, hvis det er dyrere."""
    if shelf and key in shelf:
        return float(shelf[key]["price"])
    base = NORMAL_PRICES[key][0]
    typical = (market or {}).get(key)
    return float(round(max(base, min(typical, base * MARKET_MAX_FACTOR)))) if typical else float(base)


# Varetyperne fra sammenligningen på tværs af butikker, hvis basispris står
# under et andet navn
_GROUP_BASIS = {"letmaelk": "maelk", "minimaelk": "maelk", "soedmaelk": "maelk", "spaghetti": "pasta",
                "skyr": "yoghurt"}


def offer_basis_key(heading: str, unit: str | None) -> str | None:
    """Basisvaren, et tilbud kan holdes op mod, når avisen ikke oplyser en
    normalpris, fx "hakket_okse" for "Netto hakket oksekød 8-12%".

    Bruger den strenge genkendelse fra sammenligningen på tværs af butikker
    (ikke madplanens), så fx kartoffelspegepølse ikke regnes som kartofler.
    En stykpris kan kun sammenlignes for varer, der sælges pr. stk.
    """
    group = product_group(heading)
    if group is None or unit not in ("kg", "l", "stk"):
        return None
    key = _GROUP_BASIS.get(group, group)
    if key not in NORMAL_PRICES or (unit == "stk" and group not in PER_PIECE_GROUPS):
        return None
    return key


# Den mindste pakke af basisvaren i gram (eller ml), når den er større end ét
# stk: løg i net, æg i bakker, kartofler i poser. Ellers købes ét stk ad gangen.
# Madplanen bruger det til, hvad man betaler i butikken for varer uden tilbud.
BASIS_PACK_G: dict[str, float] = {
    "kyllingebryst": 500, "kyllingelaar": 1000, "poelser": 400, "koteletter": 600, "boef": 300, "laksefilet": 250,
    "hvid_fisk": 400, "fiskefrikadeller": 300, "aeg": 600, "tortilla": 320, "burgerboller": 280, "poelsebroed": 400,
    "lasagneplader": 500, "kartofler": 2000, "guleroedder": 1000, "loeg": 1000, "hvidloeg": 150, "tomater": 500,
    "citron": 300, "lime": 210, "aebler": 1000, "skalotteloeg": 300, "pitabroed": 400, "roedbeder": 500,
    "pastinak": 500,
}


# Vægten af én, når en opskrift tæller varer, der sælges i bakker eller
# bundter: "10 cherrytomater" er 150 g, ikke 10 bakker
COUNT_G: dict[str, float] = {"cherrytomater": 15, "champignon": 20, "radiser": 15, "rosenkaal": 15,
                             "sukkeraerter": 6, "asparges": 20, "lasagneplader": 20}


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
_NOT_RAW_HEADING = ["syltede", "eddike", "indbagt", "kniv", "pande ", "pepsi", "cola "]

# Smagsord: et tilbud med et af dem ("Revet mexi-topping", "BBQ koteletter",
# "Skyr vanilje") bruges kun til en ingrediens, der selv nævner ordet
FLAVOR_WORDS = [
    "mexi", "mexicana", "tex", "taco", "krydret", "krydder", "chili", "hvidløg", "urte", "bbq", "barbecue",
    "marineret", "marinerede", "pesto", "trøffel", "honning", "karry", "teriyaki", "tandoori", "jalapeño",
    "jalapeno", "vanilje", "jordbær", "hindbær", "blåbær", "kokos", "chokolade", "karamel", "citron", "lime",
    "mango", "basilikum", "oregano", "paprika", "sennep", "ingefær", "soja", "sweet ", "spicy", "hot ", "gyros",
    "kebab", "røget", "kold", "varm", "paner", "veggie", "vegansk", "vegetar", "plante",
]
# Smagsord, der hører til varen og ikke ændrer den: bacon er næsten altid røget
FLAVOR_OK = {"bacon": ["røget"], "hakkede_tomater": ["basilikum", "hvidløg"], "kokosmaelk": ["kokos"]}

# Sorter, der ikke kan bytte plads. Nævner opskriften en sort, skal tilbuddet
# være samme sort eller ikke nævne nogen: til "lagret cheddar" duer "revet
# ost" og "revet cheddar", men ikke "revet mozzarella" eller "pizzatopping".
VARIETIES = {
    "revet_ost": ["cheddar", "mozzarella", "gouda", "emmentaler", "havarti", "gruyère", "gruyere", "pizza",
                  "parmesan", "danbo", "comté", "comte", "mild ", "lagret"],
    "ris": ["basmati", "jasmin", "arborio", "risotto", "grødris", "sushi", "vildris", "vild", "fuldkorn", "brun", "sort", "rød ", "røde"],
    "hvid_fisk": ["torsk", "sej", "kuller", "rødspætte", "kulmule", "pangasius", "hellefisk", "rødfisk", "skrubbe"],
    "yoghurt": ["græsk", "skyr", "drikke"],
    "salat": ["iceberg", "hjertesalat", "feldsalat", "frisée", "endivie"],
    "pasta": ["frisk", "glutenfri"],
    # Hakket lammekød, lammekølle og lammefilet kan ikke bytte plads
    "lam": ["hakket", "kølle", "culotte", "filet", "kotelet", "koteletter", "bov", "kam", "steak", "krone", "mørbrad"],
    "kalvekoed": ["mørbrad", "schnitzel", "schnitzler", "strimler", "tern", "culotte", "bov", "tykkam", "steg", "filet",
                  "cuvette", "inderlår", "småkød"],
    # En hel and er ikke andelår, og kalkunbryst er ikke underlår eller hakket kalkun.
    # En liste er ord for samme sort
    "and": [["andebryst", "bryst", "brystfilet"], ["andelår", "lår"],
            ["landand", "hel ", "andesteg", "andestege", "juleand", "and "]],
    "kalkun": [["kalkunbryst", "bryst", "brystfilet", "kalkunfilet", "schnitzel", "schnitzler", "strimler"],
               ["kalkunlår", "lår", "overlår", "underlår"], ["hakket", "hakkekød"], ["hel ", "kalkunsteg", "julekalkun"]],
    "roeget_laks": ["gravad", "varm", "varmrøget", "kold", "koldrøget"],
}


@lru_cache(maxsize=None)
def variety_groups(key: str) -> tuple[tuple[str, ...], ...]:
    """Sorterne for ingrediensen som grupper af ord, der betyder det samme."""
    return tuple((w,) if isinstance(w, str) else tuple(w) for w in VARIETIES.get(key, []))


@dataclass
class Item:
    amount: float  # til 4 personer; 0 = efter smag
    unit: str  # "g", "stk", "dåse", "dl" ...
    name: str
    keys: list[str] = field(default_factory=list)  # ingredienser fra INGREDIENTS
    main: bool = False  # retten foreslås kun, når en hovedingrediens er på tilbud
    side: str = ""  # tilbehør, madplanen lægger til: "groent", "kartofler" eller "ris"


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
    """Varerne i et varenavn. Det, der står efter "med", er tilbehør:
    "Skinkeculotte med tomat & ramsløg" er ikke tomater."""
    parts = [re.split(r"\bmed\b", p, maxsplit=1, flags=re.IGNORECASE)[0].strip()
             for p in re.split(r",|\beller\b", heading, flags=re.IGNORECASE)]
    return [p for p in parts if p and not p.startswith("-")]


def _matches(tokens: list[str], spec: tuple[str, list[list[str]], list[str]]) -> bool:
    _, patterns, exclude = spec
    if any(_has_word(tokens, w) for w in exclude):
        return False
    return any(all(_has_word(tokens, w) for w in pattern) for pattern in patterns)


# Mere præcise ingredienser, der vinder over en bredere: står der
# "revet parmesan", er det parmesan og ikke en hvilken som helst revet ost
REPLACES = {"okse_tern": ["oksesteg"], "oksemoerbrad": ["moerbrad", "boef"], "hvid_fisk": ["boef"],
            "chorizo": ["poelser"], "hakket_kylling": ["kyllingebryst", "kyllingelaar"], "ricotta": ["revet_ost"], "mascarpone": ["revet_ost"], "halloumi": ["revet_ost"], "parmesan": ["revet_ost"], "frisk_mozzarella": ["revet_ost"], "romaine": ["salat"], "rucola": ["salat"], "cherrytomater": ["tomater"],
            "foraarsloeg": ["loeg"], "skalotteloeg": ["loeg"], "pastinak": ["persille"], "knoldselleri": ["bladselleri"],
            "sukkeraerter": ["aerter"], "hvide_boenner": ["groenne_boenner"], "soede_kartofler": ["kartofler"],
            "pitabroed": ["broed"]}


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


@lru_cache(maxsize=None)
def _flavor_ok(key: str) -> tuple[str, ...]:
    """Smagsord, der er ingrediensens eget navn ("citron" i citroner) eller
    står i FLAVOR_OK."""
    own = [w for w in FLAVOR_WORDS if any(t.strip().casefold().startswith(w.strip())
                                          for pattern in INGREDIENTS[key][1] for t in pattern)]
    return tuple(FLAVOR_OK.get(key, [])) + tuple(own)


def offer_fits(line: str, heading: str, key: str) -> bool:
    """Kan tilbuddet bruges som ``key`` til ingrediensen ``line``?

    Nej, hvis tilbuddet har en smag, ingrediensen ikke nævner ("Revet
    mexi-topping" til "lagret cheddarost"), er en anden sort (VARIETIES), eller
    er kød til en vegetarisk ingrediens ("veggie bacon").
    Nævner tilbuddet flere varer, er det nok, at én af dem passer.
    """
    want = _tokens(line)
    veggie = any(_has_word(want, w) for w in VEGGIE_WORDS)
    ok_words = _flavor_ok(key)
    sorts = variety_groups(key)
    wanted = {n for n, group in enumerate(sorts) if any(_has_word(want, w) for w in group)}
    for part in _parts(heading):
        if key not in _ingredient_keys(part):
            continue
        tokens = _tokens(part)
        if any(_has_word(tokens, w) and not _has_word(want, w) for w in FLAVOR_WORDS if w not in ok_words):
            continue
        # "veggie bacon" er ikke bacon
        if veggie and key in _MEAT_KEYS and not any(_has_word(tokens, w) for w in VEGGIE_WORDS):
            continue
        got = {n for n, group in enumerate(sorts) if any(_has_word(tokens, w) for w in group)}
        if wanted and got and not got & wanted:
            continue
        return True
    return False


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
    "foraarsloeg", "linser", "skalotteloeg", "aubergine", "soede_kartofler", "pak_choi", "asparges", "pastinak",
    "butternut", "fennikel", "knoldselleri", "groenkaal", "rosenkaal", "radiser", "roedbeder", "boennespirer",
    "sukkeraerter", "kikaerter", "hvide_boenner",
}

# Kostrådene anbefaler omkring 600 g frugt og grønt om dagen. En ret med
# mindre end dette pr. person får en portion grønt tilbehør.
MIN_VEG_PER_PERSON = 125

# Tilbehøret: det billigste af disse, der er på tilbud
SIDE = Item(500, "g", "grønt tilbehør, fx råkost, salat eller dampet broccoli",
            ["guleroedder", "spidskaal", "broccoli", "agurk", "tomater", "salat", "groenne_boenner", "aerter"], side="groent")

# Energi i kcal pr. 100 g (rå vare). En aftensmad skal mætte: en ret uden
# kartofler, ris, pasta, brød eller lignende får kartofler eller ris som
# tilbehør, og en ret med for lidt mad i er ikke en aftensmad.
KCAL: dict[str, float] = {
    "hakket_okse": 200, "hakket_gris": 200, "hakket_gris_kalv": 190, "hakket_kylling": 140, "kyllingebryst": 110,
    "kyllingelaar": 190, "hel_kylling": 160, "bacon": 330, "stegeflaesk": 400, "medister": 300, "flaeskesteg": 250,
    "moerbrad": 120, "koteletter": 200, "ribben": 280, "svinekam": 180, "skinkekoed": 120, "lufttoerret_skinke": 250, "poelser": 250,
    "chorizo": 400, "boef": 150, "okse_tern": 150, "oksesteg": 140, "oksemoerbrad": 130, "kalvekoed": 120, "lam": 230,
    "kalkun": 110, "and": 200, "laksefilet": 200, "roeget_laks": 180, "hvid_fisk": 80, "fiskefrikadeller": 180,
    "tun": 150, "rejer": 90, "aeg": 140, "maelk": 45, "floede": 300, "creme_fraiche": 250, "revet_ost": 350,
    "frisk_mozzarella": 250, "parmesan": 400, "feta": 270, "yoghurt": 60, "smoer": 740, "pasta": 360,
    "lasagneplader": 360, "ris": 350, "nudler": 360, "tortilla": 300, "burgerboller": 270, "poelsebroed": 270,
    "pizzadej": 250, "hakkede_tomater": 25, "kidneyboenner": 100, "kokosmaelk": 180, "linser": 330, "majs": 80,
    "kartofler": 75, "guleroedder": 35, "loeg": 40, "foraarsloeg": 30, "hvidloeg": 140, "porrer": 30, "tomater": 20,
    "cherrytomater": 25, "agurk": 12, "peberfrugt": 30, "broccoli": 35, "blomkaal": 25, "spidskaal": 25,
    "roedkaal": 30, "champignon": 22, "spinat": 22, "salat": 15, "romaine": 15, "rucola": 25, "bladselleri": 15,
    "avocado": 200, "groenne_boenner": 30, "aerter": 80, "squash": 17, "wokgroent": 35, "citron": 30, "lime": 30,
    "mango": 60, "persille": 40, "aebler": 50, "skalotteloeg": 70, "aubergine": 25, "soede_kartofler": 85,
    "pak_choi": 15, "asparges": 20, "pastinak": 60, "butternut": 45, "fennikel": 30, "knoldselleri": 25,
    "groenkaal": 45, "rosenkaal": 40, "radiser": 15, "roedbeder": 45, "boennespirer": 30, "sukkeraerter": 40,
    "kikaerter": 120, "hvide_boenner": 100, "tofu": 130, "ricotta": 150, "mascarpone": 430, "flodeost": 250,
    "hytteost": 90, "halloumi": 320, "gedeost": 300, "couscous": 360, "bulgur": 350, "quinoa": 360,
    "perlebyg": 350, "gnocchi": 160, "butterdej": 400, "pitabroed": 270, "broed": 260,
}

# Det mættende i en ret: står ingen af disse i retten, får den kartofler
# eller ris som tilbehør
STARCH = {"kartofler", "soede_kartofler", "ris", "pasta", "lasagneplader", "nudler", "tortilla", "burgerboller",
          "poelsebroed", "pizzadej", "couscous", "bulgur", "quinoa", "perlebyg", "gnocchi", "butterdej",
          "pitabroed", "broed"}
# Mættende ting, madplanen ikke kan prissætte, men som retten har
STARCH_WORDS = ["polenta", "kartoffelmos", "mos ", "brød", "ris ", "nudler", "pasta", "tortilla", "wraps", "pommes",
                "fritter", "spelt", "hirse", "freekeh", "ramen", "udon", "soba", "risotto", "naan", "pita",
                "lefse", "dej ", "gær "]
# Retter, der selv er det mættende, selvom opskriften ikke nævner det ("Tarte flambée" med gær og mel)
STARCH_NAMES = ["pizza", "pizzaer", "tærte", "tærter", "tarte", "quiche", "lasagne", "risotto", "pasta", "wrap", "wraps",
                "taco", "tacos", "burrito", "burritos", "sandwich", "calzone", "pie", "pirogger", "dumplings",
                "gnocchi", "nudler", "nudelsuppe", "ramen", "flammkuchen", "focaccia", "toast", "pandekager"]
# Ord, der ikke er noget mættende, selvom de nævner det: "ris wine eddike", "rismel"
_NOT_STARCH = ["eddike", "vin", "wine", "mel ", "rismel", "papir", "stivelse", "krummer", "rasp", "crumbs", "mælk",
               "milk", "flager"]
# Så meget mættende skal retten have (kcal til 4 personer), for at den ikke får tilbehør
MIN_STARCH_KCAL = 250
# Retter, der får ris i stedet for kartofler
RICE_WORDS = ["karry", "curry", "wok", "chili", "thai", "indisk", "asiatisk", "dhal", "dahl", "dal ", "tikka",
              "masala", "teriyaki", "korma", "satay", "stroganoff", "sursød", "kokos", "soja", "sojasauce",
              "fiskesauce", "garam", "ingefær", "gochujang", "jambalaya", "bulgogi", "kung", "stir", "sambal",
              "østerssauce", "hoisin", "rendang", "vindaloo", "madras", "biryani", "gumbo"]
# Chili som krydderi gør ikke retten til en chiliret; kun i navnet eller varerne
RICE_NOT_PANTRY = ["chili"]
RICE_KEYS = ["kokosmaelk", "pak_choi", "boennespirer", "tofu"]
STARCH_SIDES = {
    "kartofler": Item(1000, "g", "kartofler som tilbehør", ["kartofler"], side="kartofler"),
    "ris": Item(300, "g", "ris som tilbehør", ["ris"], side="ris"),
}
# En hentet opskrift er en aftensmad, når dens egne varer giver mindst så
# mange kcal pr. person (uden tilbehør og det, man har derhjemme)
MIN_DINNER_KCAL = 120


def _grams(item: Item) -> float:
    if item.unit == "g":
        return item.amount
    if item.unit == "dl":
        return item.amount * 100
    return item.amount * NORMAL_PRICES[item.keys[0]][1]


def vegetables_per_person(items: list[Item]) -> float:
    """Gram grøntsager pr. person i en ret til 4."""
    return sum(_grams(i) for i in items if i.keys and i.keys[0] in VEGETABLES) / 4


def kcal_per_person(items: list[Item]) -> float:
    """Energien pr. person i en ret til 4 fra de varer, der kan genkendes."""
    return sum(_grams(i) * KCAL[i.keys[0]] / 100 for i in items if i.keys and i.amount) / 4


def starch_side(recipe: Recipe) -> Item | None:
    """Kartofler eller ris til en ret uden noget mættende, fx en flæskesteg
    eller en karry, hvor opskriften ikke nævner tilbehøret."""
    starch = sum(_grams(i) * KCAL[i.keys[0]] / 100 for i in recipe.items
                 if i.amount and any(k in STARCH for k in i.keys))
    if starch >= MIN_STARCH_KCAL:
        return None
    if any(t.endswith(w) for t in _tokens(recipe.name) for w in STARCH_NAMES):
        return None
    others = [i.name for i in recipe.items if not i.keys] + list(recipe.pantry)
    if any(_has_any(text, STARCH_WORDS) and not _has_any(text, _NOT_STARCH) for text in others):
        return None
    text = " ".join([recipe.name, *(i.name for i in recipe.items)])
    rice = (_has_any(text, RICE_WORDS) or _has_any(" ".join(recipe.pantry), [w for w in RICE_WORDS if w not in RICE_NOT_PANTRY])
            or any(k in RICE_KEYS for i in recipe.items for k in i.keys))
    return STARCH_SIDES["ris" if rice else "kartofler"]


def recipe_items(recipe: Recipe) -> list[Item]:
    """Rettens varer, med grønt tilbehør, hvis den har for lidt grønt, og
    kartofler eller ris, hvis den ikke har noget mættende."""
    items = list(recipe.items)
    if (starch := starch_side(recipe)) is not None:
        items.append(starch)
    if vegetables_per_person(recipe.items) < MIN_VEG_PER_PERSON:
        items.append(SIDE)
    return items


def dish_head(name: str) -> list[str]:
    """Ordene i det, retten er: "Kylling i karrysauce med ris" -> ["kylling"].
    "Pesto- og gedeost-spaghetti" er spaghetti: "og" efter en bindestreg deler ikke."""
    head = re.split(r"\s(?:med|i|på|til|with|in|on|uden)\s|(?<!-)\s(?:og)\s|[,|&(]", f" {name} ", maxsplit=1,
                    flags=re.IGNORECASE)[0]
    return _tokens(head) or _tokens(name)


# Supper og salater skal have mere i sig for at være en aftensmad
LIGHT_HEADS = ["suppe", "salat", "salater", "bowl", "soup", "salad"]
MIN_LIGHT_KCAL = 250
# En aftensmad har protein: kød, fisk, æg, bælgfrugter, tofu eller ost (gram til 4 personer)
PROTEIN_KEYS = {"aeg", "kidneyboenner", "linser", "kikaerter", "hvide_boenner", "tofu", "feta", "halloumi", "hytteost",
                "ricotta", "revet_ost", "frisk_mozzarella", "parmesan", "gedeost"}
MIN_PROTEIN_G = 60
# Kød og fisk pr. person i en ret med kød eller fisk. Under det er mængden
# næsten altid læst forkert ("1 lakseside" som én laksefilet, "80 g laks" til
# fire), og prisen bliver alt for lav. Bacon, chorizo og skinke giver smag
# og tæller ikke.
MIN_MEAT_PER_PERSON_G = 30
FLAVOR_MEAT_KEYS = {"bacon", "chorizo", "lufttoerret_skinke", "poelser", "roeget_laks", "rejer", "tun"}


# Bagværk og desserter: en ret uden kød eller fisk med et af disse ord er sød
# (græskartærte med vanilje og flormelis, kranse med marcipan). Kanel, kakao
# og rosiner står også i karry og chili, så de tæller ikke.
SWEET_WORDS = ["marcipan", "flormelis", "vanilje", "glasur", "frosting", "nougat", "remonce", "mazarin",
               "syltetøj", "marmelade", "vaniljesukker", "kagecreme", "konditorcreme"]


def dinner_problem(recipe: Recipe) -> str:
    """Hvorfor en hentet opskrift ikke er en aftensmad, eller "" hvis den er."""
    if recipe.kind == "vegetar":
        text = _tokens(" ".join([i.name for i in recipe.items] + list(recipe.pantry)))
        if any(_has_word(text, w) for w in SWEET_WORDS):
            return "en dessert eller bagværk"
    head = dish_head(recipe.name)
    light = bool(head) and any(head[-1].endswith(w) for w in LIGHT_HEADS)
    if kcal_per_person(recipe.items) < (MIN_LIGHT_KCAL if light else MIN_DINNER_KCAL):
        return "for lidt mad til en aftensmad"
    protein = sum(_grams(i) for i in recipe.items
                  if i.amount and any(k in PROTEIN_KEYS or k in _MEAT_KEYS for k in i.keys))
    if protein < MIN_PROTEIN_G:
        return "intet kød, fisk, æg, bælgfrugter eller ost"
    meat = [i for i in recipe.items if i.amount and i.keys and i.keys[0] in _MEAT_KEYS]
    if meat and not any(i.keys[0] in FLAVOR_MEAT_KEYS for i in meat) \
            and sum(_grams(i) for i in meat) / 4 < MIN_MEAT_PER_PERSON_G:
        return "for lidt kød eller fisk til en aftensmad (mængden er nok læst forkert)"
    return ""


def _item_payload(i: Item) -> dict:
    # Basispris og vægt pr. stk følger med ingredienserne (ingredients_payload)
    return {"amount": _amount(i.amount), "unit": i.unit, "name": i.name, "keys": i.keys, "main": i.main,
            "side": i.side or False}


def _compact_item(i: dict) -> list | str:
    """En vare i data.json: [mængde, enhed, navn, ingredienser, hovedingrediens],
    og tilbehøret bare som "groent", "kartofler" eller "ris". Browseren pakker
    dem ud igen (loadPlanData i app.html); det gør data.json halvt så stor."""
    if i["side"]:
        return i["side"]
    return [i["amount"], i["unit"], i["name"], i["keys"], 1 if i["main"] else 0]


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


def _english_name(name: str) -> bool:
    """Et engelsk navn på en dansk madside, som ikke kunne oversættes:
    "Alpine chicken schnitzel with fresh lemon and creamy potatoes"."""
    return bool(re.search(r"\bwith\b", name, re.IGNORECASE)) and not re.search(
        r"\b(?:med|og|i|på|til)\b", name, re.IGNORECASE)


def unique_recipes(recipes) -> list[Recipe]:
    """Opskrifterne uden dubletter og uden engelske navne. Madsider som
    HelloFresh har samme ret flere gange (på dansk og engelsk, eller med
    citron og med citrus); samme madside og samme varer i samme mængder er
    samme ret, og den første beholdes."""
    seen: set = set()
    result = []
    for r in recipes:
        if _english_name(r.name):
            continue
        key = (urlparse(r.source).netloc,
               tuple(sorted((i.keys[0], round(i.amount), i.unit) for i in r.items if i.keys)))
        if key in seen:
            continue
        seen.add(key)
        result.append(r)
    return result


def recipes_payload() -> list[dict]:
    """Retterne som siden og appen bruger dem: de faste og dem fra madsiderne."""
    return [_recipe_payload(r) for r in [*RECIPES, *unique_recipes(imported_recipes())]]


# -- Afdelinger ---------------------------------------------------------
# Hvor i butikken ingrediensen står (samme navne som kategorierne), så
# indkøbslisten kan følge vejen gennem butikken
_DEPARTMENT_KEYS = {
    "koed": ["hakket_okse", "hakket_gris", "hakket_gris_kalv", "hakket_kylling", "kyllingebryst", "kyllingelaar",
             "hel_kylling", "bacon", "stegeflaesk", "medister", "flaeskesteg", "moerbrad", "koteletter", "ribben", "poelser",
             "boef", "okse_tern", "chorizo", "svinekam", "skinkekoed", "lufttoerret_skinke", "oksesteg", "oksemoerbrad",
             "kalvekoed", "lam", "kalkun", "and"],
    "fisk": ["laksefilet", "roeget_laks", "hvid_fisk", "fiskefrikadeller", "rejer"],
    "mejeri": ["aeg", "maelk", "floede", "creme_fraiche", "revet_ost", "frisk_mozzarella", "parmesan", "feta", "yoghurt", "smoer",
               "pizzadej", "tofu", "ricotta", "mascarpone", "flodeost", "hytteost", "halloumi", "gedeost", "butterdej"],
    "broed_og_bager": ["tortilla", "burgerboller", "poelsebroed", "pitabroed", "broed"],
    "frost": ["aerter", "wokgroent"],
    "kolonial": ["pasta", "lasagneplader", "ris", "nudler", "hakkede_tomater", "kidneyboenner", "kokosmaelk",
                 "majs", "tun", "linser", "kikaerter", "hvide_boenner", "couscous", "bulgur", "quinoa", "perlebyg",
                 "gnocchi"],
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
    # Ikke kød eller fisk at købe, selv om ordet ligner: "risvin" er ikke svin, "kødsnor" er snor
    "risvin", "mirin", "kødsnor", "fiskesause", "nori", "tang ", "ansjos", "ansjoser", "katsuobushi",
]
PORK_WORDS = ["skinke", "bacon", "pancetta", "chorizo", "salami", "svin", "gris", "flæsk", "pølse", "prosciutto",
              "serrano", "medister", "kotelet", "spegepølse", "ribben", "spareribs",
              # Engelske ord, som oversættelsen lader stå
              "pork", "pepperoni", "nduja", "ham ", "gammon", "lardons", "hamburgerryg", "kassler",
              "guanciale", "mortadella", "salsiccia", "frankfurter", "wienerpølse", "revelsben"]
FISH_WORDS = ["fisk", "laks", "torsk", "tun ", "rejer", "makrel", "sild", "ansjos", "muslinge", "hummer",
              "krabbe", "blæksprutte", "rødspætte", "kuller", "sej ", "skaldyr", "kammusling", "tang ", "lyssej",
              "mørksej", "kulmule", "hellefisk", "rødfisk", "havkat", "ørred", "pighvar", "rødtunge", "skrubbe ",
              "sardin", "havbars", "dorade", "havrude", "bass", "seabass", "bream", "monkfish", "halibut", "haddock",
              "cod ", "salmon", "prawn", "prawns", "shrimp", "squid", "calamari", "mussels", "clams", "scallops",
              # Flere fisk, så en ret med dem aldrig ligner en vegetarret
              "multe", "brosme", "stenbider", "rognkelse", "hornfisk", "hvilling", "ising", "helleflynder",
              "rokke", "aborre", "gedde", "sandart", "karpe", "ål ", "østers ", "krebs", "rogn", "kaviar", "søtunge",
              "tilapia", "pangasius", "mullet", "trout", "mackerel", "sardine", "anchov", "tuna", "fiskefond",
              "tunbøf", "tunfilet", "havtaske", "slethvar", "victoria", "isingfilet", "jomfruhummer", "knurhane",
              "katsuobushi"]
MEAT_WORDS = ["kød", "okse", "kalv", "lam", "kylling", "kalkun", "and ", "andebryst", "gås", "vildt", "hjort",
              "rådyr", "kanin", "bøf", "andesteg", "juleand", "chicken", "beef", "turkey", "lamb", "meatball",
              "meatballs", "pulled", "bresaola", "venison", "duck", "frikadelle", "høne", "hønse", "lever", "kebab", "gyros", "steak", "tournedos", "gulasch", "gullasch",
              "entrecote", "entrecôte", "culotte", "cuvette", "ribeye", "picanha", "sirloin", "hakkebøf", "kæbe",
              "fasan", "perlehøne", "agerhøne", "goose", "vildsvin", "gedekød", "fårekød", "struds", "bison", "dådyr",
              "kronhjort"]
_KIND_KEYS = [
    ("fisk", ["laksefilet", "roeget_laks", "hvid_fisk", "fiskefrikadeller", "tun", "rejer"]),
    # And og kalkun er fjerkræ ligesom kylling; kalv og lam er rødt kød ligesom okse
    ("kylling", ["hakket_kylling", "kyllingebryst", "kyllingelaar", "hel_kylling", "kalkun", "and"]),
    ("okse", ["hakket_okse", "boef", "okse_tern", "oksesteg", "oksemoerbrad", "kalvekoed", "lam"]),
    ("gris", ["hakket_gris", "hakket_gris_kalv", "bacon", "stegeflaesk", "medister", "flaeskesteg", "moerbrad",
              "koteletter", "poelser", "chorizo", "svinekam", "skinkekoed", "lufttoerret_skinke", "ribben"]),
]
_MEAT_KEYS = {k for _, keys in _KIND_KEYS for k in keys}
KIND_OF = {k: kind for kind, keys in _KIND_KEYS for k in keys}


def _has_any(text: str, words: list[str]) -> bool:
    tokens = _tokens(text)
    return any(_has_word(tokens, w) for w in words)


# "veggie bøffer" og "plantefars" er ikke kød
VEGGIE_WORDS = ["veggie", "vegansk", "vegetar", "plante"]


def diet_flag(text: str) -> str:
    """ "pork", "fish" eller "meat", hvis linjen nævner kød eller fisk."""
    if _has_any(text, VEGGIE_WORDS):
        return ""
    for flag, words in (("pork", PORK_WORDS), ("fish", FISH_WORDS), ("meat", MEAT_WORDS)):
        if _has_any(text, words):
            return flag
    return ""


# Navne, der lyder af kød uden at være det: "linsebøf", "uden kød" og
# engelske navne som "Mac and cheese", hvor "and" ikke er en and
_VEGGIE_NAME = re.compile(r"(grøntsags|grønsags|linse|bønne|kikærte|rødbede|squash|svampe|kartoffel)bøf|uden kød|\band\b",
                          re.IGNORECASE)


# Ansjoser er krydderi: "Pasta med broccoli og ansjos" er en grøntsagsret med fisk i smagen
_SEASONING_NAME = re.compile(r"\bansjos\w*", re.IGNORECASE)


def _meat_in_name(name: str) -> bool:
    """Om rettens navn nævner kød eller fisk, man skal købe."""
    return bool(diet_flag(_SEASONING_NAME.sub(" ", _VEGGIE_NAME.sub(" ", name))))


def _last_word(tokens: list[str], words: list[str]) -> tuple[int, int]:
    """Hvor det sidste af ordene står: (ordets plads, om det står sidst i ordet)."""
    return max(((i, int(t.endswith(w.strip().casefold()))) for w in words for i, t in enumerate(tokens)
                if _has_word([t], w)), default=(-1, 0))


def _seasoning(text: str) -> bool:
    """Om en linje med kød eller fisk er bouillon, sauce eller krydderi. Det,
    der står sidst, er varen: "kyllingebouillon" og "fiskesauce" er basisvarer,
    men "peberspegepølse" og "honning skinke" er kød. Det efter "til" og
    "fra" er ikke varen: "Salt til kød", "Stegesky fra kyllingen"."""
    text = re.sub(r"\([^)]*\)?|\band/or\b", " ", text).replace("fiske sauce", "fiskesauce")
    tokens = _tokens(re.split(r",|\b(?:til|till|fra)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]) or _tokens(text)
    meat = _last_word(tokens, PORK_WORDS + FISH_WORDS + MEAT_WORDS)
    pantry = _last_word(tokens, PANTRY_WORDS)
    return pantry >= meat and pantry[0] >= 0


def _before_til(name: str) -> str:
    """Det, der står før "til": i "salt til ris" er varen salt, ikke ris."""
    return re.split(r"\btil\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip() or name


# Hver vare i en ingredienslinje: "hvidløg og persille" er to varer
_ITEM_SPLIT = re.compile(r",|/|&|\b(?:og|eller|and|or|with)\b", re.IGNORECASE)


def _key_position(key: str, tokens: list[str]) -> tuple[int, int]:
    """Hvor ingrediensen står i teksten: det sidste ord, den matcher, og om
    den står sidst i ordet ("asparges|kartofler")."""
    best = (-1, 0)
    for pattern in INGREDIENTS[key][1]:
        if not all(_has_word(tokens, w) for w in pattern):
            continue
        for word in pattern:
            w = word.strip().casefold()
            for i, t in enumerate(tokens):
                if _has_word([t], word):
                    best = max(best, (i, int(t.endswith(w))))
    return best


def line_keys(name: str) -> list[str]:
    """Ingredienserne i en ingredienslinje (uden mængde). En mere præcis
    ingrediens vinder i hele linjen: "parmesanost, revet" er parmesan, ikke
    også revet ost. Nævner én vare flere ingredienser, er det den sidste,
    der er varen, og de andre beskriver den: "løg pølser" er pølser,
    "majs tortillas" er tortillas og "æg tomater" er tomater."""
    text = _before_til(name)
    keys = ingredient_keys(text)
    replaced = {r for k in keys for r in REPLACES.get(k, [])}
    keys = [k for k in keys if k not in replaced]
    if len(keys) < 2:
        return keys
    heads: set[str] = set()
    others: set[str] = set()
    # Det i parentes er valgmuligheder: "hakket kød (okse eller grise- og kalv)"
    for part in _ITEM_SPLIT.split(re.sub(r"\([^)]*\)?", " ", text)):
        here = [k for k in ingredient_keys(part) if k in keys]
        tokens = _tokens(part)
        where = {k: _key_position(k, tokens) for k in here}
        last = max(where.values(), default=None)
        # Står to ingredienser i samme ord ("hakket kød"), tæller begge
        heads.update(k for k in here if where[k] == last)
        others.update(k for k in here if where[k] != last)
    return [k for k in keys if k in heads or k not in others]


# En kendt vare uden mængde ("hakkede tomater", "kogte ris til servering")
# skal købes: med mængden i teksten ("polpa 400g"), ellers en almindelig
# mængde til 4 personer, og ellers ét stk eller én pakke. Kun det valgfrie og
# smør til stegning regnes for at være derhjemme.
_QTY_IN_TEXT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(g|gr|gram|kg|ml|cl|dl|l)(?![\w])", re.IGNORECASE)
OPTIONAL_WORDS = ["evt", "eventuelt", "valgfrit", "valgfri", "optional", "efter smag", "til stegning", "til pynt",
                  "til pensling", "til smøring", "til friture", "til drys", "til panering", "lidt", "en smule",
                  "et skvæt", "skvæt", "håndfuld", "knivspids", "nip", "drys"]
_OPTIONAL_RE = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in OPTIONAL_WORDS) + r")(?!\w)", re.IGNORECASE)
MISSING_PANTRY = {"smoer", "maelk"}
# "1 pakke", "2 poser", "1 net": en hel pakke af varen (BASIS_PACK_G)
_PACK_RE = re.compile(r"^\s*(?:ca\.?\s*)?[\d½¼¾⅓⅔][\d\s.,/½¼¾⅓⅔-]*(pakke|pakker|pk|bakke|bakker|pose|poser|net|bundt|bundter|bdt)\.?(?=\s|$)",
                      re.IGNORECASE)
DEFAULT_AMOUNTS: dict[str, tuple[float, str]] = {
    "ris": (300, "g"), "pasta": (400, "g"), "kartofler": (1000, "g"), "soede_kartofler": (800, "g"),
    "couscous": (300, "g"), "bulgur": (300, "g"), "quinoa": (300, "g"), "perlebyg": (300, "g"), "nudler": (250, "g"),
    "gnocchi": (500, "g"), "hvidloeg": (2, "fed"), "tortilla": (8, "stk"), "pitabroed": (4, "stk"),
    "burgerboller": (4, "stk"), "poelsebroed": (8, "stk"), "aeg": (4, "stk"), "floede": (2, "dl"),
    "yoghurt": (500, "g"),
}


def missing_amount(line: str, text: str, key: str) -> tuple[float, str]:
    """Mængden af en kendt vare, når linjen ikke har en. (0, "") betyder derhjemme."""
    if key in MISSING_PANTRY or _OPTIONAL_RE.search(line):
        return 0.0, ""
    if (m := _QTY_IN_TEXT.search(text)):
        unit, factor = UNITS[m[2].lower()]
        return float(m[1].replace(",", ".")) * factor, unit
    if key in DEFAULT_AMOUNTS:
        return DEFAULT_AMOUNTS[key]
    # Kød og fisk: en almindelig portion til 4, eller ét stk af en steg eller en hel kylling
    if key in KIND_OF and NORMAL_PRICES[key][1] < 500:
        return 500.0, "g"
    return 1.0, "stk"


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
            staple = _seasoning(text) if flag else _has_any(text, PANTRY_WORDS)
            if flag and not staple:
                return None, f"ukendt kød eller fisk: {text}"
            if flag and flag not in flags:
                flags.append(flag)
            # Små mængder ("4 g Tex-Mex", "1 tsk røget paprika") er krydderier
            small = unit == "g" and amount <= 10
            (pantry if staple or small or not amount else unknown).append(text)
            continue
        if not amount:
            amount, unit = missing_amount(line, text, keys[0])
            if not amount:
                # "Smør til stegning", "evt. persille" og lignende: regnes for at være derhjemme
                pantry.append(text)
                continue
            if not _QTY_IN_TEXT.search(text):  # en almindelig mængde til 4 personer
                amount /= scale
        elif unit in ("stk", "bundt") and _PACK_RE.match(line) and (
                basis_pack_g(keys[0]) > NORMAL_PRICES[keys[0]][1] or keys[0] in COUNT_G):
            # "1 pakke grillpølser" er en hel pakke, ikke én pølse
            amount, unit = amount * basis_pack_g(keys[0]), "g"
        elif unit == "stk" and keys[0] in COUNT_G:
            amount, unit = amount * COUNT_G[keys[0]], "g"
        amount *= scale
        if unit == "stk" and not NORMAL_PRICES[keys[0]][1]:
            amount, unit = amount * DEFAULT_PIECE_G, "g"
        if unit == "g" and keys[0] in LIQUIDS:  # "2 spsk mælk" er 0,3 dl, ikke 30 g
            amount, unit = amount / 100, "dl"
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
    # "Lynstegt rumpsteak ..." uden kendt kød i ingredienserne: kødet kan
    # ikke prissættes, og retten må ikke ligne en vegetarret på tilbud
    if kind == "vegetar" and _meat_in_name(name):
        return None, f"kød eller fisk i navnet, men ikke i ingredienserne: {name}"
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
    except FileNotFoundError:
        return []
    # En ødelagt fil (fx en halvt flettet fra GitHub) skal stoppe byggeriet i
    # stedet for at give en side uden opskrifter og links til madsiderne
    return json.loads(text).get("recipes", [])


MAX_MINUTES = 600


@lru_cache(maxsize=1)
def imported_recipes() -> tuple[Recipe, ...]:
    """Opskrifterne fra madsiderne, der er aftensmad. Reglerne bruges også på
    opskrifter, der blev hentet, før reglerne blev skærpet."""
    from .opskrifter import clean_name, is_dinner
    from .oversaet import danish

    result = []
    for data in load_imported():
        data, _ = danish(data)  # engelske opskrifter på dansk
        if data is None or not is_dinner(data):
            continue
        recipe, _ = recipe_from_lines(
            "web-" + hashlib.sha1(data["url"].encode()).hexdigest()[:10], clean_name(data["name"]), data["ingredients"],
            # Over 10 timer er marinering eller optøning, ikke tiden i køkkenet
            data.get("persons") or 4, m if (m := data.get("minutes") or 0) <= MAX_MINUTES else 0, "", data["url"],
        )
        if recipe and not dinner_problem(recipe):
            result.append(recipe)
    return tuple(result)


def ingredients_payload(market: dict[str, float] | None = None, shelf: dict[str, dict] | None = None) -> list[dict]:
    """Ingredienserne med mønstre, så browseren kan læse egne opskrifter.
    ``src`` siger, hvor en rigtig hyldepris kommer fra; uden den er prisen anslået."""
    shelf = shelf or {}
    return [
        {"key": k, "name": name, "patterns": patterns, "exclude": exclude,
         "price": [basis_price(k, market, shelf), NORMAL_PRICES[k][1]],
         **({"src": {f: shelf[k][f] for f in ("store", "product", "pack", "shelf")}} if k in shelf else {}),
         "pack": basis_pack_g(k), "veg": k in VEGETABLES, "dept": department(k), "replaces": REPLACES.get(k, []),
         "kcal": KCAL[k], **({"kind": KIND_OF[k]} if k in KIND_OF else {}), **({"starch": True} if k in STARCH else {}),
         **({"default": list(DEFAULT_AMOUNTS[k])} if k in DEFAULT_AMOUNTS else {}),
         **({"missing_pantry": True} if k in MISSING_PANTRY else {}),
         **({"count_g": COUNT_G[k]} if k in COUNT_G else {})}
        for k, (name, patterns, exclude) in INGREDIENTS.items()
    ]


def plan_payload(market: dict[str, float] | None = None, shelf: dict[str, dict] | None = None) -> dict:
    """Alt, madplanen i browseren skal bruge. ``market`` er market_prices for
    tilbuddene i prishistorikken, ``shelf`` de rigtige hyldepriser."""
    return {
        "recipes": [{**r, "items": [_compact_item(i) for i in r["items"]]} for r in recipes_payload()],
        "ingredients": ingredients_payload(market, shelf),
        "side": _item_payload(SIDE),
        "starch_sides": {k: _item_payload(i) for k, i in STARCH_SIDES.items()},
        "starch_words": STARCH_WORDS, "rice_words": RICE_WORDS, "rice_keys": RICE_KEYS,
        "not_starch": _NOT_STARCH, "rice_not_pantry": RICE_NOT_PANTRY, "min_starch_kcal": MIN_STARCH_KCAL, "starch_names": STARCH_NAMES,
        "optional": OPTIONAL_WORDS,
        "words": {"not_raw": _NOT_RAW, "not_raw_heading": _NOT_RAW_HEADING, "pantry": PANTRY_WORDS,
                  "flavor": FLAVOR_WORDS, "flavor_ok": {k: list(_flavor_ok(k)) for k in INGREDIENTS if _flavor_ok(k)},
                  "varieties": {k: [list(g) for g in variety_groups(k)] for k in VARIETIES},
                  "pork": PORK_WORDS, "fish": FISH_WORDS, "meat": MEAT_WORDS, "veggie": VEGGIE_WORDS},
        "min_veg": MIN_VEG_PER_PERSON,
        "piece_g": DEFAULT_PIECE_G,
        "units": {u: list(v) for u, v in UNITS.items()},
    }
