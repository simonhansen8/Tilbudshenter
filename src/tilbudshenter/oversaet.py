"""Engelske opskrifter på dansk.

Opskrifter fra engelske madsider gemmes, som de står, og oversættes, når de
bruges. Så gælder en bedre oversættelse også de opskrifter, der allerede er
hentet. Oversættelsen er en ordliste, ikke en maskinoversætter: mængderne
regnes om til danske enheder (cups til dl, oz til g, tbsp til spsk), og
ingredienserne får de danske navne, som tilbudsaviserne bruger.

En opskrift, hvis navn ikke kan oversættes helt, eller som nævner kød eller
fisk, ordlisten ikke kender, bruges ikke. Hellere færre opskrifter end
halvt engelske navne eller en svinekødsret, der ligner en vegetarret.
"""

from __future__ import annotations

import re
import unicodedata

# -- Mængder og enheder -----------------------------------------------------
_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8",
              "⅞": "7/8", "⅕": "1/5"}
_NUM = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?"
# Engelsk enhed -> (dansk enhed, faktor)
UNITS: dict[str, tuple[str, float]] = {
    "cup": ("dl", 2.4), "cups": ("dl", 2.4), "c": ("dl", 2.4),
    "tbsp": ("spsk", 1), "tbsps": ("spsk", 1), "tbs": ("spsk", 1), "tablespoon": ("spsk", 1),
    "tablespoons": ("spsk", 1), "tbl": ("spsk", 1), "tb": ("spsk", 1),
    "tsp": ("tsk", 1), "tsps": ("tsk", 1), "teaspoon": ("tsk", 1), "teaspoons": ("tsk", 1),
    "oz": ("g", 28.35), "ounce": ("g", 28.35), "ounces": ("g", 28.35),
    "lb": ("g", 453.6), "lbs": ("g", 453.6), "pound": ("g", 453.6), "pounds": ("g", 453.6),
    "g": ("g", 1), "gr": ("g", 1), "gram": ("g", 1), "grams": ("g", 1), "kg": ("kg", 1), "kgs": ("kg", 1),
    "ml": ("ml", 1), "millilitres": ("ml", 1), "milliliters": ("ml", 1), "l": ("l", 1), "litre": ("l", 1),
    "litres": ("l", 1), "liter": ("l", 1), "liters": ("l", 1), "cl": ("cl", 1),
    "clove": ("fed", 1), "cloves": ("fed", 1),
    "can": ("dåse", 1), "cans": ("dåse", 1), "tin": ("dåse", 1), "tins": ("dåse", 1),
    "jar": ("glas", 1), "jars": ("glas", 1),
    "bunch": ("bundt", 1), "bunches": ("bundt", 1),
    "pack": ("pakke", 1), "packs": ("pakke", 1), "packet": ("pakke", 1), "packets": ("pakke", 1),
    "package": ("pakke", 1), "packages": ("pakke", 1), "bag": ("pose", 1), "bags": ("pose", 1),
    "slice": ("skiver", 1), "slices": ("skiver", 1), "rasher": ("skiver", 1), "rashers": ("skiver", 1),
    "pinch": ("knivspids", 1), "pinches": ("knivspids", 1), "dash": ("knivspids", 1),
    "handful": ("håndfuld", 1), "handfuls": ("håndfuld", 1),
    "sprig": ("kvist", 1), "sprigs": ("kvist", 1), "stick": ("stk", 1), "sticks": ("stk", 1),
    "head": ("stk", 1), "heads": ("stk", 1), "unit": ("stk", 1), "units": ("stk", 1), "gm": ("g", 1),
    "gms": ("g", 1), "milliliter": ("ml", 1), "millilitre": ("ml", 1), "pkt": ("pakke", 1), "pkts": ("pakke", 1),
    "pint": ("dl", 5.7), "pints": ("dl", 5.7), "qt": ("dl", 9.5), "quart": ("dl", 9.5), "punnet": ("bakke", 1),
    "punnets": ("bakke", 1), "sachet": ("pakke", 1), "sachets": ("pakke", 1), "carton": ("pakke", 1),
    "cartons": ("pakke", 1), "tub": ("bæger", 1), "tubs": ("bæger", 1), "box": ("pakke", 1), "boxes": ("pakke", 1),
    "block": ("pakke", 1), "ball": ("stk", 1), "balls": ("stk", 1), "bulb": ("stk", 1), "bulbs": ("stk", 1),
    "knob": ("g", 15), "knobs": ("g", 15), "fl": ("ml", 29.6), "whole": ("stk", 1), "wedge": ("stk", 1),
    "wedges": ("stk", 1), "piece": ("stk", 1), "pieces": ("stk", 1),
    "fillet": ("stk", 1), "fillets": ("stk", 1), "breast": ("stk", 1), "breasts": ("stk", 1),
    "thigh": ("stk", 1), "thighs": ("stk", 1), "stalk": ("stk", 1), "stalks": ("stk", 1),
    "large": ("stk", 1), "medium": ("stk", 1), "small": ("stk", 1),
}
# Enheder, der ikke er en vægt, men hører til ingrediensen: "2 chicken breasts"
_NOUN_UNITS = {"unit", "units", "whole", "ball", "balls", "bulb", "bulbs", "wedge", "wedges", "fillet", "fillets", "breast", "breasts", "thigh", "thighs", "stalk", "stalks", "large", "medium",
               "small", "head", "heads"}

# -- Ingredienser ---------------------------------------------------------
# Engelsk -> dansk. Længste udtryk vinder, så "chicken breast" ikke bliver
# "kylling bryst". Navnene er dem, mealplan.INGREDIENTS og tilbudsaviserne bruger.
WORDS: dict[str, str] = {
    # Kød
    "beef mince": "hakket oksekød", "minced beef": "hakket oksekød", "ground beef": "hakket oksekød",
    "lean beef mince": "hakket oksekød", "lean minced beef": "hakket oksekød", "lean ground beef": "hakket oksekød",
    "pork mince": "hakket grisekød", "minced pork": "hakket grisekød", "ground pork": "hakket grisekød",
    "chicken mince": "hakket kyllingekød", "minced chicken": "hakket kyllingekød", "ground chicken": "hakket kyllingekød",
    "turkey mince": "hakket kalkunkød", "minced turkey": "hakket kalkunkød", "ground turkey": "hakket kalkunkød",
    "lamb mince": "hakket lammekød", "minced lamb": "hakket lammekød", "ground lamb": "hakket lammekød",
    "mince": "hakket oksekød", "minced meat": "hakket oksekød",
    "chicken breast fillets": "kyllingebryst", "chicken breast fillet": "kyllingebryst",
    "chicken breasts": "kyllingebryst", "chicken breast": "kyllingebryst", "chicken fillets": "kyllingebryst",
    "chicken fillet": "kyllingebryst", "chicken tenderloins": "kyllingeinderfilet", "chicken mini fillets": "kyllingeinderfilet",
    "chicken thigh fillets": "kyllingelårfilet", "chicken thighs": "kyllingelår", "chicken thigh": "kyllingelår",
    "chicken legs": "kyllingelår", "chicken drumsticks": "kyllingeunderlår", "drumsticks": "kyllingeunderlår",
    "whole chicken": "hel kylling", "chicken": "kylling", "chickens": "kyllinger",
    "bacon": "bacon", "streaky bacon": "bacon", "smoked bacon": "bacon", "bacon lardons": "bacon i tern",
    "lardons": "bacon i tern", "pancetta": "pancetta", "chorizo": "chorizo", "sausages": "pølser", "sausage": "pølser",
    "pork sausages": "pølser", "pork chops": "koteletter", "pork chop": "koteletter", "pork loin": "svinekam",
    "pork tenderloin": "mørbrad", "pork fillet": "mørbrad", "pork belly": "stegeflæsk", "pork shoulder": "svinekød",
    "pork": "svinekød", "ham": "skinke", "gammon": "skinke", "prosciutto": "prosciutto", "parma ham": "parmaskinke",
    "serrano ham": "serranoskinke",
    "beef steak": "bøf", "steaks": "bøffer", "steak": "bøf", "sirloin steak": "bøf", "ribeye steak": "ribeye",
    "rump steak": "bøf", "fillet steak": "oksemørbrad", "beef fillet": "oksemørbrad", "beef tenderloin": "oksemørbrad",
    "stewing beef": "oksekød i tern", "braising steak": "oksekød i tern", "diced beef": "oksekød i tern",
    "beef chuck": "oksekød i tern", "chuck steak": "oksekød i tern", "beef strips": "oksestrimler", "beef": "oksekød",
    "lamb leg": "lammekølle", "leg of lamb": "lammekølle", "lamb shoulder": "lammebov", "lamb chops": "lammekoteletter",
    "lamb": "lammekød", "duck breasts": "andebryst", "duck breast": "andebryst", "duck legs": "andelår", "duck": "and",
    "turkey breast": "kalkunbryst", "turkey": "kalkun", "veal": "kalvekød",
    "meatballs": "kødboller",
    # Fisk
    "salmon fillets": "laksefilet", "salmon fillet": "laksefilet", "salmon": "laks", "smoked salmon": "røget laks",
    "hot-smoked salmon": "varmrøget laks", "hot smoked salmon": "varmrøget laks",
    "cod fillets": "torskefilet", "cod fillet": "torskefilet", "cod": "torsk", "haddock": "kuller",
    "pollock": "sej", "hake": "kulmule", "white fish fillets": "fiskefilet", "white fish": "fiskefilet",
    "basa": "pangasius", "plaice": "rødspætte", "tuna": "tun", "tinned tuna": "tun", "canned tuna": "tun",
    "tuna steaks": "tunbøffer", "prawns": "rejer", "king prawns": "rejer", "raw prawns": "rejer",
    "shrimp": "rejer", "shrimps": "rejer", "mackerel": "makrel", "smoked mackerel": "røget makrel",
    "mussels": "muslinger", "anchovies": "ansjoser", "anchovy": "ansjoser", "fish sauce": "fiskesauce",
    "fish": "fisk", "trout": "ørred", "sardines": "sardiner", "squid": "blæksprutte", "crab": "krabbe",
    "scallops": "kammuslinger",
    # Mejeri og æg
    "eggs": "æg", "egg": "æg", "egg yolks": "æggeblommer", "egg yolk": "æggeblomme", "egg whites": "æggehvider",
    "milk": "mælk", "whole milk": "sødmælk", "semi-skimmed milk": "letmælk", "skimmed milk": "skummetmælk",
    "buttermilk": "kærnemælk", "double cream": "piskefløde", "heavy cream": "piskefløde", "whipping cream": "piskefløde",
    "single cream": "madlavningsfløde", "light cream": "madlavningsfløde", "cream": "fløde", "thickened cream": "piskefløde",
    "sour cream": "creme fraiche", "soured cream": "creme fraiche", "crème fraîche": "creme fraiche",
    "creme fraiche": "creme fraiche", "half-fat crème fraîche": "creme fraiche",
    "butter": "smør", "unsalted butter": "usaltet smør", "salted butter": "smør",
    "cheddar": "revet cheddar", "grated cheddar": "revet cheddar", "mature cheddar": "revet cheddar",
    "cheddar cheese": "revet cheddar", "grated cheese": "revet ost", "cheese": "revet ost",
    "shredded cheese": "revet ost", "mozzarella": "revet mozzarella", "grated mozzarella": "revet mozzarella",
    "shredded mozzarella": "revet mozzarella", "fresh mozzarella": "frisk mozzarella",
    "mozzarella ball": "frisk mozzarella", "parmesan": "parmesan", "grated parmesan": "revet parmesan",
    "parmesan cheese": "parmesan", "pecorino": "pecorino", "feta": "feta", "feta cheese": "feta",
    "halloumi": "halloumi", "ricotta": "ricotta", "mascarpone": "mascarpone", "cream cheese": "flødeost", "cottage cheese": "hytteost",
    "goat's cheese": "gedeost", "goats cheese": "gedeost", "paneer": "paneer",
    "greek yogurt": "græsk yoghurt", "greek yoghurt": "græsk yoghurt", "natural yogurt": "yoghurt naturel",
    "natural yoghurt": "yoghurt naturel", "plain yogurt": "yoghurt naturel", "yogurt": "yoghurt", "yoghurt": "yoghurt",
    # Kolonial
    "spaghetti": "spaghetti", "penne": "penne", "fusilli": "fusilli", "rigatoni": "rigatoni", "linguine": "linguine",
    "tagliatelle": "tagliatelle", "macaroni": "makaroni", "pasta": "pasta", "orzo": "orzo",
    "lasagne sheets": "lasagneplader", "lasagna sheets": "lasagneplader", "lasagna noodles": "lasagneplader",
    "egg noodles": "ægnudler", "rice noodles": "risnudler", "noodles": "nudler", "udon noodles": "udonnudler",
    "rice": "ris", "long-grain rice": "ris", "long grain rice": "ris", "basmati rice": "basmatiris",
    "jasmine rice": "jasminris", "risotto rice": "risottoris", "arborio rice": "risottoris", "brown rice": "brune ris",
    "couscous": "couscous", "bulgur": "bulgur", "quinoa": "quinoa",
    "tortillas": "tortillas", "tortilla wraps": "tortillas", "wraps": "tortillas", "flour tortillas": "tortillas",
    "burger buns": "burgerboller", "brioche buns": "burgerboller", "hot dog buns": "pølsebrød", "pitta": "pitabrød",
    "pitta breads": "pitabrød", "pita bread": "pitabrød", "naan": "naanbrød", "naan bread": "naanbrød",
    "pizza dough": "pizzadej", "puff pastry": "butterdej", "shortcrust pastry": "tærtedej", "breadcrumbs": "rasp",
    "panko breadcrumbs": "panko", "panko": "panko", "bread": "brød", "crusty bread": "brød",
    "chopped tomatoes": "hakkede tomater", "tinned tomatoes": "hakkede tomater", "canned tomatoes": "hakkede tomater",
    "diced tomatoes": "hakkede tomater", "crushed tomatoes": "hakkede tomater", "plum tomatoes": "flåede tomater",
    "whole peeled tomatoes": "flåede tomater", "passata": "passata", "tomato passata": "passata",
    "tomato purée": "tomatpuré", "tomato puree": "tomatpuré", "tomato paste": "tomatpuré",
    "tomato sauce": "tomatsauce", "kidney beans": "kidneybønner", "black beans": "sorte bønner",
    "cannellini beans": "cannellinibønner", "butter beans": "smørbønner", "chickpeas": "kikærter",
    "baked beans": "baked beans", "red lentils": "røde linser", "green lentils": "grønne linser",
    "lentils": "linser", "puy lentils": "grønne linser", "coconut milk": "kokosmælk", "coconut cream": "kokosfløde",
    "sweetcorn": "majs", "corn": "majs", "corn kernels": "majskerner",
    "chicken stock": "hønsebouillon", "chicken broth": "hønsebouillon", "beef stock": "oksebouillon",
    "beef broth": "oksebouillon", "vegetable stock": "grøntsagsbouillon", "vegetable broth": "grøntsagsbouillon",
    "stock cube": "bouillonterning", "stock cubes": "bouillonterninger", "stock": "bouillon", "fish stock": "fiskebouillon",
    "olive oil": "olivenolie", "extra virgin olive oil": "olivenolie", "vegetable oil": "olie", "sunflower oil": "solsikkeolie",
    "rapeseed oil": "rapsolie", "groundnut oil": "olie", "peanut oil": "olie", "canola oil": "rapsolie",
    "kosher salt": "salt", "flaky salt": "salt", "flaky sea salt": "havsalt", "table salt": "salt", "fine salt": "salt", "oil": "olie", "sesame oil": "sesamolie", "coconut oil": "kokosolie",
    "plain flour": "hvedemel", "all-purpose flour": "hvedemel", "flour": "hvedemel", "self-raising flour": "hvedemel",
    "cornflour": "majsstivelse", "cornstarch": "majsstivelse", "sugar": "sukker", "caster sugar": "sukker",
    "brown sugar": "brun farin", "granulated sugar": "sukker", "white sugar": "sukker", "icing sugar": "flormelis",
    "powdered sugar": "flormelis", "light brown sugar": "brun farin", "soft brown sugar": "brun farin", "honey": "honning",
    "maple syrup": "ahornsirup", "salt": "salt", "sea salt": "havsalt", "black pepper": "sort peber",
    "pepper": "peber", "salt and pepper": "salt og peber", "salt and black pepper": "salt og peber",
    "soy sauce": "sojasauce", "light soy sauce": "sojasauce", "dark soy sauce": "mørk sojasauce",
    "oyster sauce": "østerssauce", "hoisin sauce": "hoisinsauce", "sweet chilli sauce": "sød chilisauce",
    "sweet chili sauce": "sød chilisauce", "sriracha": "sriracha", "worcestershire sauce": "worcestershiresauce",
    "dijon mustard": "dijonsennep", "wholegrain mustard": "grov sennep", "mustard": "sennep",
    "mayonnaise": "mayonnaise", "mayo": "mayonnaise", "ketchup": "ketchup", "bbq sauce": "barbecuesauce",
    "barbecue sauce": "barbecuesauce", "red wine vinegar": "rødvinseddike", "white wine vinegar": "hvidvinseddike",
    "balsamic vinegar": "balsamico", "cider vinegar": "æblecidereddike", "apple cider vinegar": "æblecidereddike",
    "rice vinegar": "riseddike", "vinegar": "eddike", "red wine": "rødvin", "white wine": "hvidvin",
    "dry white wine": "hvidvin", "pesto": "pesto", "green pesto": "grøn pesto", "red pesto": "rød pesto",
    "curry paste": "karrypasta", "red curry paste": "rød karrypasta", "green curry paste": "grøn karrypasta",
    "thai red curry paste": "rød karrypasta", "thai green curry paste": "grøn karrypasta",
    "harissa": "harissa", "tahini": "tahin", "peanut butter": "jordnøddesmør", "peanuts": "jordnødder",
    "cashews": "cashewnødder", "cashew nuts": "cashewnødder", "almonds": "mandler", "flaked almonds": "mandelflager",
    "pine nuts": "pinjekerner", "walnuts": "valnødder", "sesame seeds": "sesamfrø", "capers": "kapers",
    "olives": "oliven", "black olives": "sorte oliven", "green olives": "grønne oliven", "green olive": "grønne oliven",
    "harissa paste": "harissa", "chilli paste": "chilipasta", "tikka paste": "tikkapasta", "curry leaves": "karryblade", "kalamata olives": "kalamataoliven",
    "sun-dried tomatoes": "soltørrede tomater", "sundried tomatoes": "soltørrede tomater", "raisins": "rosiner",
    "water": "vand", "boiling water": "kogende vand", "cold water": "koldt vand", "ice": "is",
    # Krydderier og krydderurter
    "garlic": "hvidløg", "garlic cloves": "fed hvidløg", "garlic clove": "fed hvidløg", "ginger": "ingefær",
    "fresh ginger": "frisk ingefær", "chilli": "chili", "chili": "chili", "chillies": "chili", "red chilli": "rød chili",
    "green chilli": "grøn chili", "chilli flakes": "chiliflager", "chili flakes": "chiliflager",
    "red pepper flakes": "chiliflager", "chilli powder": "chilipulver", "chili powder": "chilipulver",
    "cayenne pepper": "cayennepeber", "cayenne": "cayennepeber", "paprika": "paprika", "smoked paprika": "røget paprika",
    "sweet paprika": "paprika", "cumin": "spidskommen", "ground cumin": "stødt spidskommen", "cumin seeds": "spidskommenfrø",
    "coriander": "koriander", "ground coriander": "stødt koriander", "fresh coriander": "frisk koriander",
    "cilantro": "frisk koriander", "turmeric": "gurkemeje", "ground turmeric": "stødt gurkemeje",
    "garam masala": "garam masala", "curry powder": "karry", "cinnamon": "kanel", "ground cinnamon": "stødt kanel",
    "cinnamon stick": "kanelstang", "nutmeg": "muskatnød", "cloves (spice)": "nelliker", "allspice": "allehånde",
    "cardamom": "kardemomme", "cardamom pods": "kardemommekapsler", "star anise": "stjerneanis",
    "bay leaves": "laurbærblade", "bay leaf": "laurbærblad", "thyme": "timian", "fresh thyme": "frisk timian",
    "dried thyme": "tørret timian", "rosemary": "rosmarin", "oregano": "oregano", "dried oregano": "tørret oregano",
    "basil": "basilikum", "fresh basil": "frisk basilikum", "basil leaves": "basilikumblade", "parsley": "persille",
    "flat-leaf parsley": "bredbladet persille", "flat leaf parsley": "bredbladet persille", "fresh parsley": "frisk persille",
    "mint": "mynte", "fresh mint": "frisk mynte", "dill": "dild", "chives": "purløg", "sage": "salvie",
    "tarragon": "estragon", "lemongrass": "citrongræs", "lemongrass stalk": "citrongræs", "kaffir lime leaves": "limeblade",
    "lime leaves": "limeblade", "italian seasoning": "italiensk krydderi", "mixed herbs": "tørrede krydderurter",
    "dried mixed herbs": "tørrede krydderurter", "herbs": "krydderurter", "fennel seeds": "fennikelfrø",
    "mustard seeds": "sennepsfrø", "onion powder": "løgpulver", "garlic powder": "hvidløgspulver",
    "five-spice": "fem krydderier", "chinese five-spice": "fem krydderier", "vanilla extract": "vaniljeekstrakt",
    "baking powder": "bagepulver", "bicarbonate of soda": "natron", "baking soda": "natron", "yeast": "gær",
    # Frugt og grønt
    "onion": "løg", "onions": "løg", "brown onion": "løg", "brown onions": "løg", "yellow onion": "løg",
    "yellow onions": "løg", "white onion": "løg", "white onions": "løg", "red onion": "rødløg", "red onions": "rødløg",
    "spring onions": "forårsløg", "spring onion": "forårsløg", "green onions": "forårsløg", "green onion": "forårsløg",
    "scallions": "forårsløg", "shallots": "skalotteløg", "shallot": "skalotteløg", "leek": "porre", "leeks": "porrer",
    "carrot": "gulerod", "carrots": "gulerødder", "potato": "kartoffel", "potatoes": "kartofler",
    "new potatoes": "nye kartofler", "baby potatoes": "små kartofler", "floury potatoes": "kartofler",
    "waxy potatoes": "kartofler", "sweet potato": "sød kartoffel", "sweet potatoes": "søde kartofler",
    "tomato": "tomat", "tomatoes": "tomater", "cherry tomatoes": "cherrytomater", "grape tomatoes": "cherrytomater",
    "cucumber": "agurk", "red pepper": "rød peberfrugt", "red peppers": "røde peberfrugter",
    "yellow pepper": "gul peberfrugt", "green pepper": "grøn peberfrugt", "peppers": "peberfrugter",
    "bell pepper": "peberfrugt", "bell peppers": "peberfrugter", "red bell pepper": "rød peberfrugt",
    "capsicum": "peberfrugt", "red capsicum": "rød peberfrugt", "broccoli": "broccoli", "tenderstem broccoli": "broccolini",
    "cauliflower": "blomkål", "cabbage": "hvidkål", "white cabbage": "hvidkål", "red cabbage": "rødkål",
    "savoy cabbage": "savoykål", "pointed cabbage": "spidskål", "mushrooms": "champignon", "mushroom": "champignon",
    "chestnut mushrooms": "brune champignon", "button mushrooms": "champignon", "spinach": "spinat",
    "baby spinach": "babyspinat", "kale": "grønkål", "lettuce": "salat", "iceberg lettuce": "icebergsalat",
    "romaine lettuce": "romainesalat", "little gem lettuce": "hjertesalat", "rocket": "rucola", "arugula": "rucola",
    "celery": "bladselleri", "celery sticks": "bladselleri", "celery stalks": "bladselleri", "avocado": "avocado",
    "avocados": "avocado", "green beans": "grønne bønner", "fine beans": "grønne bønner", "peas": "ærter",
    "frozen peas": "frosne ærter", "petits pois": "ærter", "courgette": "squash", "courgettes": "squash",
    "zucchini": "squash", "aubergine": "aubergine", "aubergines": "auberginer", "eggplant": "aubergine",
    "butternut squash": "butternutsquash", "pumpkin": "græskar", "beetroot": "rødbeder", "beets": "rødbeder",
    "parsnips": "pastinakker", "parsnip": "pastinak", "asparagus": "asparges", "fennel": "fennikel",
    "pak choi": "pak choi", "bok choy": "pak choi", "bean sprouts": "bønnespirer", "edamame": "edamamebønner",
    "corn on the cob": "majskolber", "stir-fry vegetables": "wokgrøntsager", "mixed vegetables": "blandede grøntsager",
    "lemon": "citron", "lemons": "citroner", "lime": "lime", "limes": "lime", "lemon juice": "citronsaft",
    "lime juice": "limesaft", "lemon zest": "citronskal", "lime zest": "limeskal", "orange": "appelsin",
    "apple": "æble", "apples": "æbler", "mango": "mango", "pineapple": "ananas", "coriander leaves": "frisk koriander",
    "jalapeño": "jalapeño", "jalapeños": "jalapeños", "jalapeno": "jalapeño", "jalapenos": "jalapeños",
}
# Ord, der beskriver tilberedning: oversættes, hvis de står før varen
ADJECTIVES = {
    "fresh": "frisk", "dried": "tørret", "frozen": "frosne", "chopped": "hakket", "finely": "", "roughly": "",
    "diced": "i tern", "sliced": "i skiver", "grated": "revet", "minced": "hakket", "crushed": "knust",
    "large": "", "small": "", "medium": "", "big": "", "ripe": "moden", "boneless": "", "skinless": "",
    "skin-on": "", "lean": "", "free-range": "", "organic": "", "good-quality": "", "good": "",
    "quality": "", "thinly": "", "thickly": "", "freshly": "", "ground": "stødt", "toasted": "ristet", "cooked": "kogt",
    "leftover": "", "raw": "rå", "peeled": "skrællet", "smoked": "røget", "unsalted": "usaltet", "whole": "hel",
    "baby": "", "tinned": "", "canned": "", "drained": "", "rinsed": "", "softened": "", "melted": "smeltet",
    "beaten": "pisket", "shredded": "revet", "halved": "halveret", "quartered": "i kvarte", "trimmed": "",
    "extra": "", "heaped": "", "level": "", "generous": "", "about": "ca.", "approx": "ca.", "approximately": "ca.",
    "handful": "en håndfuld", "handfuls": "en håndfuld", "pinch": "en knivspids", "cold": "", "cubed": "i tern", "filtered": "", "and": "og", "chunks": "",
    "chunk": "", "pieces": "", "piece": "", "florets": "buketter", "leaves": "blade", "white": "hvid", "dark": "mørk",
    "in": "i", "flakes": "flager", "pitted": "uden sten", "vine-ripened": "", "long": "", "fresh,": "frisk",
    "x": "", "of": "", "a": "", "an": "", "plus": "", "some": "", "few": "", "the": "",
}

# Kød og fisk, som ingen oversættelse må overse. Står et af ordene tilbage
# på engelsk, bruges opskriften ikke.
ENGLISH_MEAT = ["beef", "pork", "chicken", "lamb", "turkey", "duck", "bacon", "ham", "gammon", "sausage", "fish",
                "salmon", "cod", "prawn", "shrimp", "tuna", "mince", "steak", "chorizo", "anchov", "crab", "lobster",
                "mussel", "squid", "venison", "veal", "pancetta", "prosciutto", "salami", "meat", "goat", "rabbit",
                "haddock", "mackerel", "sardine", "scallop", "clam", "oyster", "brisket", "rib", "ribs", "pepperoni",
                "liver", "kidney", "oxtail", "pheasant", "quail", "pigeon", "lard", "suet", "gelatine", "gelatin"]
# "kidney beans" og "fish sauce" er ikke kød: de står i WORDS og er oversat, før der tjekkes

# -- Navne --------------------------------------------------------------
# Ord i opskriftens navn. Står der et ord i navnet, som hverken er her, i
# WORDS eller i DISHES, bruges opskriften ikke.
TITLE_WORDS: dict[str, str] = {
    "with": "med", "and": "og", "&": "og", "in": "i", "on": "på", "of": "med", "for": "til", "or": "eller",
    "a": "", "an": "", "the": "", "easy": "nem", "quick": "hurtig", "simple": "nem", "best": "", "ultimate": "",
    "perfect": "", "classic": "klassisk", "healthy": "sund", "healthier": "sundere", "homemade": "hjemmelavet",
    "creamy": "cremet", "crispy": "sprød", "crunchy": "sprød", "spicy": "stærk", "sticky": "klistret", "smoky": "røget",
    "cheesy": "med ost", "garlicky": "med hvidløg", "lemony": "med citron", "herby": "med krydderurter",
    "honey": "honning", "garlic": "hvidløg", "lemon": "citron", "roast": "ovnstegt", "roasted": "ovnbagt",
    "baked": "bagt", "grilled": "grillet", "fried": "stegt", "pan-fried": "pandestegt", "stuffed": "fyldt",
    "slow-cooker": "langtidskogt", "slow": "langtids", "cooker": "", "slow-cooked": "langtidskogt",
    "trykkoger": "i trykkoger", "airfryer": "i airfryer", "bradepande": "på bradepande",
    "braised": "braiseret", "pulled": "pulled", "one-pot": "i én gryde", "one-pan": "på én pande", "traybake": "i fad",
    "tray": "", "bake": "i fad", "sheet": "", "pan": "pande", "skillet": "på pande", "stew": "gryde", "casserole": "gryderet",
    "soup": "suppe", "salad": "salat", "curry": "karry", "pie": "tærte", "pies": "tærter", "burger": "burger",
    "burgers": "burgere", "meatballs": "kødboller", "meatball": "kødboller", "skewers": "spyd", "kebabs": "spyd",
    "stir-fry": "wok", "stir": "", "fry": "wok", "noodles": "nudler", "rice": "ris", "fried rice": "stegte ris",
    "bowl": "skål", "bowls": "skåle", "wraps": "wraps", "wrap": "wrap", "sandwich": "sandwich", "tacos": "tacos",
    "traybake,": "i fad", "gratin": "gratin", "hash": "hash", "fritters": "frikadeller", "patties": "bøffer",
    "cakes": "frikadeller", "fishcakes": "fiskefrikadeller", "fish cakes": "fiskefrikadeller", "chips": "pommes frites",
    "mash": "mos", "mashed": "mos", "gravy": "sovs", "sauce": "sauce", "dressing": "dressing", "bake,": "i fad",
    "veggie": "vegetar", "vegetarian": "vegetar", "vegan": "vegansk", "vegetable": "grøntsags", "vegetables": "grøntsager",
    "veg": "grønt", "summer": "sommer", "winter": "vinter", "autumn": "efterårs", "spring": "forårs", "family": "familie",
    "mexican": "mexicansk", "italian": "italiensk", "thai": "thai", "indian": "indisk", "chinese": "kinesisk",
    "japanese": "japansk", "korean": "koreansk", "greek": "græsk", "moroccan": "marokkansk", "spanish": "spansk",
    "french": "fransk", "vietnamese": "vietnamesisk", "middle": "mellemøstlig", "eastern": "", "cajun": "cajun",
    "mediterranean": "middelhavs", "asian": "asiatisk", "style": "", "inspired": "", "-style": "", "speedy": "hurtig",
    "lighter": "lettere", "light": "let", "big": "stor", "mini": "mini", "loaded": "fyldt", "fiery": "stærk",
    "sweet": "sød", "sour": "sur", "hot": "stærk", "sesame": "sesam", "peanut": "jordnødde", "coconut": "kokos",
    "tomato": "tomat", "tomatoes": "tomater", "potato": "kartoffel", "potatoes": "kartofler", "lentil": "linse",
    "bean": "bønne", "beans": "bønner", "chickpea": "kikærte", "chickpeas": "kikærter", "mushroom": "champignon",
    "mushrooms": "champignon", "cheese": "ost", "pepper": "peber", "peppers": "peberfrugter", "herb": "krydderurte",
    "herbs": "krydderurter", "green": "grøn", "red": "rød", "black": "sort", "white": "hvid", "brown": "brun",
    "butter": "smør", "mustard": "sennep", "chilli": "chili", "chili": "chili", "ginger": "ingefær", "lime": "lime",
    "orange": "appelsin", "maple": "ahorn", "pesto": "pesto", "parmesan": "parmesan", "feta": "feta",
    "halloumi": "halloumi", "mozzarella": "mozzarella", "spinach": "spinat", "broccoli": "broccoli",
    "cauliflower": "blomkål", "squash": "græskar", "pumpkin": "græskar", "leek": "porre", "carrot": "gulerod",
    "sweetcorn": "majs", "corn": "majs", "pea": "ærte", "peas": "ærter", "avocado": "avocado", "egg": "æg", "eggs": "æg",
    "tray-bake": "i fad", "and,": "og", "warm": "lun", "golden": "gylden", "steamed": "dampet", "sautéed": "sauteret",
    "sauteed": "sauteret", "glazed": "glaseret", "crusted": "paneret", "breaded": "paneret", "shredded": "revet",
    "smashed": "smadrede", "mixed": "blandet", "air": "", "fryer": "airfryer", "air-fryer": "airfryer",
    "instant": "", "oven": "ovn", "oven-baked": "ovnbagt", "pan-roasted": "pandestegt", "minute": "minutters",
    "minutes": "minutters", "super": "", "double": "", "cooked": "kogt", "balls": "kugler", "tenderloin": "mørbrad",
    "leg": "kølle", "kale": "grønkål", "citrus": "citrus", "olive": "oliven", "olives": "oliven", "scallion": "forårsløg",
    "cheeseburger": "cheeseburger", "cheeseburgers": "cheeseburgere", "chipotle": "chipotle", "turkish": "tyrkisk",
    "sicilian": "siciliansk", "louisiana": "", "southwest": "", "lankan": "", "sri": "", "comforting": "",
    "outrageous": "", "next": "", "level": "", "dream": "", "melt-in-the-mouth": "", "no-chop": "", "one-step": "",
    "all-american": "amerikansk", "american": "amerikansk", "british": "britisk", "english": "engelsk",
    "irish": "irsk", "scottish": "skotsk", "cuban": "cubansk", "caribbean": "caribisk", "hawaiian": "hawaiiansk",
    "persian": "persisk", "lebanese": "libanesisk", "turkish-style": "tyrkisk", "portuguese": "portugisisk",
    "german": "tysk", "swedish": "svensk", "nordic": "nordisk", "scandi": "nordisk", "tuscan": "toscansk",
    "provençal": "provencalsk", "malaysian": "malaysisk", "indonesian": "indonesisk", "filipino": "filippinsk",
    "peruvian": "peruviansk", "brazilian": "brasiliansk", "ethiopian": "etiopisk", "west": "", "african": "afrikansk",
    "texas": "texas", "tex-mex": "tex-mex", "southern": "", "new": "", "baby": "", "whole": "hel", "half": "halv",
    "sharing": "", "family-friendly": "", "weeknight": "hverdags", "midweek": "hverdags", "lunchbox": "",
    "buttery": "smøret", "zesty": "frisk", "fresh": "frisk", "tangy": "syrlig", "savoury": "", "savory": "",
    "rich": "fyldig", "hearty": "mættende", "chunky": "grov", "rustic": "rustik", "simple,": "nem", "lean": "mager",
    "low-calorie": "let", "low-fat": "let", "high-protein": "proteinrig", "protein": "protein", "gluten-free": "glutenfri",
    "dairy-free": "mælkefri", "keto": "keto", "paleo": "paleo", "budget": "billig", "cheap": "billig",
    "freezable": "", "make-ahead": "", "leftover": "rester", "leftovers": "rester", "shortcut": "", "cheat's": "",
    "lazy": "nem", "speedy,": "hurtig", "fakeaway": "takeaway", "takeaway": "takeaway", "street": "street",
    "food": "food", "broad": "", "bok": "pak", "choy": "choi", "pak": "pak", "choi": "choi", "kohlrabi": "glatkål",
    "brussels": "rosen", "sprout": "kål", "sprouts": "kål", "beetroot": "rødbede", "beet": "rødbede", "beets": "rødbeder",
    "parsnip": "pastinak", "parsnips": "pastinakker", "aubergine": "aubergine", "eggplant": "aubergine",
    "courgette": "squash", "zucchini": "squash", "asparagus": "asparges", "fennel": "fennikel", "celeriac": "knoldselleri",
    "cabbage": "kål", "onion": "løg", "onions": "løg", "garlic-ginger": "hvidløg og ingefær", "lemon-garlic": "citron og hvidløg",
    "lemon-butter": "citronsmør", "lemon-herb": "citron og krydderurter", "honey-garlic": "honning og hvidløg",
    "honey-mustard": "honning og sennep", "sweet-and-sour": "sursød", "sweet-sour": "sursød", "salt": "salt",
    "pepper,": "peber", "paprika": "paprika", "cumin": "spidskommen", "turmeric": "gurkemeje", "saffron": "safran",
    "cinnamon": "kanel", "thyme": "timian", "rosemary": "rosmarin", "sage": "salvie", "basil": "basilikum",
    "parsley": "persille", "coriander": "koriander", "cilantro": "koriander", "mint": "mynte", "minty": "med mynte",
    "dill": "dild", "tarragon": "estragon", "oregano": "oregano", "chive": "purløg", "chives": "purløg",
    "walnut": "valnødde", "walnuts": "valnødder", "almond": "mandel", "almonds": "mandler", "cashew": "cashew",
    "pistachio": "pistacie", "hazelnut": "hasselnødde", "pine": "pinje", "nut": "nødde", "nuts": "nødder",
    "seed": "frø", "seeds": "frø", "apple": "æble", "apples": "æbler", "pear": "pære", "pears": "pærer",
    "pineapple": "ananas", "mango": "mango", "plum": "blomme", "plums": "blommer", "fig": "figen", "figs": "figner",
    "grape": "drue", "grapes": "druer", "pomegranate": "granatæble", "cranberry": "tranebær", "apricot": "abrikos",
    "date": "daddel", "dates": "dadler", "raisin": "rosin", "cherry": "cherry", "spring-onion": "forårsløg",
    "tofu": "tofu", "tempeh": "tempeh", "quorn": "quorn", "seitan": "seitan", "polenta": "polenta",
    "bulgur": "bulgur", "barley": "byg", "pearl": "perle", "freekeh": "freekeh", "farro": "farro", "oats": "havre",
    "oat": "havre", "cornbread": "majsbrød", "baguette": "baguette", "sourdough": "surdejs", "bun": "bolle",
    "buns": "boller", "roll": "rulle", "loaf": "brød", "crumble": "crumble", "crumb": "", "puff": "butterdejs",
    "pastry": "dej", "filo": "filo", "phyllo": "filo", "top": "", "topped": "toppet", "stew,": "gryde",
    "parcel": "pakke", "en": "en", "papillote": "papillote", "packets": "pakker", "foil": "folie", "kebab": "kebab",
    "skewer": "spyd", "platter": "fad", "board": "", "feast": "", "supper": "aftensmad", "dinner": "aftensmad",
    "lunch": "frokost", "brunch": "brunch", "breakfast": "morgenmad", "meal": "", "prep": "", "plate": "tallerken",
    "bowl,": "skål", "salsa": "salsa", "relish": "relish", "slaw": "coleslaw", "pickled": "syltet", "pickles": "pickles",
    "yogurt": "yoghurt", "yoghurt": "yoghurt", "cream": "fløde", "creamed": "cremet", "ricotta": "ricotta",
    "goat's": "gede", "goats": "gede", "blue": "blå", "brie": "brie", "camembert": "camembert", "cheddar": "cheddar",
    "gruyère": "gruyère", "gruyere": "gruyère", "manchego": "manchego", "mac": "mac", "macaroni,": "makaroni",
    "white-bean": "hvide bønner", "black-bean": "sorte bønner", "kidney": "kidney", "butter-bean": "smørbønne",
    "cannellini": "cannellini", "borlotti": "borlotti", "puy": "", "lentils": "linser", "red-lentil": "røde linser",
    "split": "flækkede", "edamame": "edamame", "beansprout": "bønnespire", "beansprouts": "bønnespirer",
    "noodle": "nudel", "soba,": "soba", "rice,": "ris", "jasmine": "jasmin", "basmati": "basmati", "coconut-milk": "kokosmælk",
    "stock": "bouillon", "broth,": "suppe", "consommé": "consommé", "bisque": "bisque", "ribs": "ribben",
    "rib": "ribben", "eye": "", "ribeye": "ribeye", "sirloin": "mørbrad", "brisket": "bryst", "short": "", "chop": "kotelet",
    "cutlets": "schnitzler", "cutlet": "schnitzel", "escalopes": "schnitzler", "escalope": "schnitzel",
    "drumsticks": "underlår", "drumstick": "underlår", "wing": "vinge", "nuggets": "nuggets", "goujons": "strimler",
    "strips": "strimler", "tenders": "strimler", "pieces": "stykker", "bites,": "bidder", "chunks": "stykker",
    "meatloaf": "farsbrød", "mince,": "hakket kød", "minced": "hakket", "ground": "hakket", "keema": "keema",
    "haddock": "kuller", "hake": "kulmule", "mackerel": "makrel", "trout": "ørred", "sea": "", "bass": "havbars",
    "bream": "dorade", "seafood": "skaldyr", "mussels": "muslinger", "clams": "muslinger", "squid": "blæksprutte",
    "calamari": "blæksprutte", "crab": "krabbe", "scallops": "kammuslinger", "king": "", "tiger": "", "shrimps": "rejer",
    "sardines": "sardiner", "anchovy": "ansjos", "anchovies": "ansjoser", "smoked": "røget", "hot-smoked": "varmrøget",
    "cured": "saltet", "gammon": "skinke", "prosciutto": "prosciutto", "pancetta": "pancetta", "salami": "salami",
    "pepperoni": "pepperoni", "meat": "kød", "meaty": "med kød", "veal": "kalv", "venison": "hjort", "pheasant": "fasan",
    "quail": "vagtel", "goose": "gås", "breast": "bryst", "breasts": "bryst", "thighs": "lår", "thigh": "lår",
    "wings": "vinger", "legs": "lår", "chops": "koteletter", "fillet": "filet", "fillets": "fileter", "loin": "kam",
    "shoulder": "skulder", "belly": "flæsk", "steak": "bøf", "steaks": "bøffer", "mince": "hakket kød",
    "chicken": "kylling", "beef": "okse", "pork": "svinekød", "lamb": "lam", "turkey": "kalkun", "duck": "and",
    "sausage": "pølser", "sausages": "pølser", "bacon": "bacon", "ham": "skinke", "salmon": "laks", "cod": "torsk",
    "prawn": "reje", "prawns": "rejer", "shrimp": "rejer", "tuna": "tun", "fish": "fisk", "chorizo": "chorizo",
    "pasta": "pasta", "spaghetti": "spaghetti", "penne": "penne", "macaroni": "makaroni", "rigatoni": "rigatoni",
    "orzo": "orzo", "gnocchi": "gnocchi", "linguine": "linguine", "tagliatelle": "tagliatelle", "lasagne": "lasagne",
    "lasagna": "lasagne", "risotto": "risotto", "pizza": "pizza", "quiche": "quiche", "tart": "tærte",
    "omelette": "omelet", "frittata": "frittata", "toast": "toast", "flatbreads": "fladbrød", "flatbread": "fladbrød",
    "dumplings": "dumplings", "rolls": "ruller", "parcels": "pakker", "bites": "bidder", "pot": "gryde",
    "hotpot": "gryde", "chowder": "suppe", "broth": "suppe", "ragu": "ragù", "ragù": "ragù", "sauce,": "sauce",
}
# Retter, der hedder det samme på dansk
DISHES = {
    "tikka", "masala", "korma", "jalfrezi", "rogan", "josh", "vindaloo", "madras", "biryani", "dal", "dhal", "daal",
    "saag", "aloo", "gobi", "paneer", "balti", "bhuna", "dopiaza", "pad", "thai", "satay", "laksa", "rendang",
    "teriyaki", "katsu", "ramen", "pho", "bibimbap", "bulgogi", "gochujang", "kimchi", "sriracha", "hoisin",
    "chow", "mein", "lo", "kung", "pao", "szechuan", "sichuan", "gyoza", "bao", "nasi", "goreng", "mee", "tom", "yum",
    "kha", "massaman", "panang", "larb", "carbonara", "bolognese", "bolognaise", "arrabbiata", "puttanesca",
    "alfredo", "primavera", "amatriciana", "cacciatore", "parmigiana", "piccata", "marsala", "saltimbocca", "milanese",
    "minestrone", "pesto", "aglio", "olio", "e", "alla", "al", "con", "carne", "chilli", "chili", "fajitas", "fajita",
    "enchiladas", "enchilada", "burrito", "burritos", "quesadilla", "quesadillas", "nachos", "taco", "tacos",
    "tostadas", "chimichurri", "jambalaya", "gumbo", "paella", "shakshuka", "shakshouka", "tagine", "harissa",
    "falafel", "hummus", "houmous", "shawarma", "kofta", "koftas", "souvlaki", "gyros", "moussaka", "stroganoff",
    "goulash", "gulasch", "schnitzel", "ratatouille", "cassoulet", "bourguignon", "coq", "au", "vin", "niçoise",
    "nicoise", "caesar", "cobb", "poke", "tonkatsu", "jerk", "piri", "peri", "tandoori", "bhaji", "bhajis",
    "samosa", "samosas", "pakora", "pakoras", "korean", "bbq", "barbecue", "sloppy", "joes", "chorizo", "halloumi",
    "feta", "gnocchi", "risotto", "lasagne", "quiche", "frittata", "orzo", "couscous", "bulgur", "quinoa", "naan",
    "pitta", "tortilla", "wellington", "kiev", "cordon", "bleu", "parmigiano", "bruschetta", "focaccia", "calzone",
    "stromboli", "panzanella", "tabbouleh", "fattoush", "dhansak", "makhani", "butter", "mapo", "tofu",
    "tempeh", "seitan", "udon", "soba", "yaki", "donburi", "katsudon", "oyakodon", "okonomiyaki", "miso",
    "pilaf", "pilau", "kedgeree", "cottage", "shepherd's", "shepherds", "toad", "hole", "bubble", "squeak",
    "bangers", "scouse", "tzatziki", "raita", "salsa", "guacamole", "slaw", "coleslaw", "ragu", "ragù", "bake", "pasties", "pasty",
}

# Engelske ord i kategorien -> dansk, så is_dinner kan læse dem
CATEGORY_WORDS = {
    "dinner": "aftensmad", "dinners": "aftensmad", "supper": "aftensmad", "main": "hovedret", "mains": "hovedretter",
    "main course": "hovedret", "main dish": "hovedret", "dessert": "dessert", "desserts": "desserter",
    "cake": "kage", "cakes": "kager", "baking": "bagværk", "bread": "brød ", "breakfast": "morgenmad",
    "brunch": "brunch", "lunch": "frokost", "snack": "snack", "snacks": "snack", "side": "tilbehør",
    "sides": "tilbehør", "side dish": "tilbehør", "starter": "forret", "starters": "forretter",
    "appetizer": "forret", "appetizers": "forretter", "drink": "drikke", "drinks": "drikke", "cocktail": "cocktail",
    "cocktails": "cocktail", "sauce": "dressing", "sauces": "dressing", "condiment": "dressing", "salad": "salat",
    "salads": "salater", "soup": "suppe", "soups": "suppe", "sweets": "konfekt", "treats": "snack",
    "cookies": "småkage", "biscuits": "småkage", "jam": "syltetøj", "preserves": "syltetøj", "smoothie": "smoothie",
    "smoothies": "smoothie", "canapes": "forret", "canapés": "forret", "party food": "snack",
}
# Navne på retter, der ikke er aftensmad, selv om kategorien siger hovedret
NOT_DINNER_EN = ["stock", "broth", "paste", "cake", "cakes", "cookie", "cookies", "brownie", "brownies", "muffin", "muffins", "cupcake",
                 "cupcakes", "biscuit", "biscuits", "pudding", "crumble", "cheesecake", "pancake", "pancakes",
                 "waffle", "waffles", "porridge", "granola", "smoothie", "cocktail", "jam", "fudge", "ice cream",
                 "sorbet", "tart tatin", "pavlova", "trifle", "scones", "loaf", "bread", "dip", "dressing",
                 "marinade", "gravy", "sauce", "rub", "seasoning", "syrup", "frosting", "icing", "cordial",
                 "lemonade", "mocktail", "punch", "eggnog", "fudge", "truffles", "bars", "doughnuts", "donuts"]


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for k, v in _FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{k}", rf"\1 {v}", text).replace(k, v)
    text = text.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def _number(text: str) -> float:
    text = text.strip().replace(",", ".")
    if " " in text:
        whole, frac = text.split(None, 1)
        return float(whole) + _number(frac)
    if "/" in text:
        a, b = text.split("/")
        return float(a) / float(b) if float(b) else 0
    return float(text)


def _fmt(value: float) -> str:
    if value >= 20:
        value = round(value / 5) * 5 if value < 1000 else round(value / 50) * 50
    value = round(value, 1)
    return (str(int(value)) if float(value).is_integer() else str(value)).replace(".", ",")


_PHRASES = sorted(WORDS, key=lambda w: -len(w))
_PHRASE_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(p) for p in _PHRASES) + r")(?![\w-])", re.IGNORECASE)


def translate_name(text: str) -> str:
    """En ingrediens på dansk, fx "boneless chicken thighs" -> "uden ben kyllingelår"."""
    text = _clean(text).lower()
    # Det efter kommaet er tilberedning ("onion, finely chopped") og gemmes ikke
    text = re.split(r";|\bfor (?:the |a )?(?:serving|garnish|frying|topping|drizzling|greasing|dusting|brushing|sprinkling)\b|"
                    r"\bto (?:serve|garnish|taste|fry)\b|\bfor the\b|\bcut into\b|\bat room temperature\b|\bsee note|\bplus extra\b|"
                    r"\bplus more\b|\bif needed\b|\bdivided\b|\bsifted\b", text)[0]
    text = re.sub(r"\((?:or|and|about|approx|optional|see|sub|use|i |we )[^)]*\)?", " ", text)
    # Det efter kommaet er som regel tilberedning ("onion, finely chopped"), men
    # ikke altid: "boneless, skinless chicken breasts"
    parts = text.split(",")
    text = next((p for p in parts if _PHRASE_RE.search(p)), parts[0])
    if text is not parts[0] and _PHRASE_RE.search(parts[0]) is None:
        text = " ".join(parts[: parts.index(text) + 1])
    text = re.sub(r"\((?:optional|see note[^)]*|note[^)]*)\)|\boptional\b", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\bor\b.*$", "", text) if " or " in text and _PHRASE_RE.search(text.split(" or ")[0]) else text
    text = re.sub(r"\b(?:and|or)\s*$", "", text.strip())
    out = []
    pos = 0
    for m in _PHRASE_RE.finditer(text):
        out += [ADJECTIVES.get(w, w) for w in text[pos:m.start()].split()]
        out.append(WORDS[m.group(1).lower()])
        pos = m.end()
    out += [ADJECTIVES.get(w, w) for w in text[pos:].split()]
    name = re.sub(r"\s+", " ", " ".join(w for w in out if w)).strip(" -()")
    name = re.sub(r" og (?=i tern|i skiver|hakket)", " ", name)
    return re.sub(r"^(?:og |eller )+|(?: og| eller)+$", "", name).strip()


def translate_line(line: str) -> str:
    """En engelsk ingredienslinje som en dansk, som mealplan.parse_line kan læse.

    "1 cup (240ml) milk" -> "2,4 dl mælk"; "400g can chopped tomatoes" -> "1 dåse hakkede tomater".
    """
    text = _clean(line)
    # Overskrifter i ingredienslisten: "For the sauce"
    if re.match(r"^(for the|for)\b.*:?$", text, re.IGNORECASE) and len(text.split()) <= 5:
        return ""
    text = re.sub(r"\((?:s|es)\)", "", text)  # "unit(s)", "milliliter(s)"
    text = re.sub(r"^\.(\d)", r"0.\1", text)
    text = re.sub(r"^(?:half|1/2)\s+(?:of\s+)?(?:an?\s+)?", "1/2 ", text, flags=re.IGNORECASE)
    text = re.sub(rf"^({_NUM})\s+an?\s+", r"\1 ", text)  # "½ a bunch"
    text = re.sub(r"(\d)\.0+\b", r"\1", text)  # "75.00 gm"
    text = re.sub(rf"({_NUM})\s+to\s+({_NUM})", r"\1-\2", text)  # "10 to 12 cups"
    # "250ml/9fl oz", "250 g / 8 oz": den første mængde bruges
    text = re.sub(r"\b(?:heaped|heaping|level|rounded|scant|generous|good|large|big|small|medium)\s+(?=(?:tbsp|tsp|tablespoons?|teaspoons?|cups?|handfuls?|pinch)\b)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(\s*[\d.,/ ]+\s*[a-zA-Z]+)\s*/\s*[\d.,/ ]+\s*(?:fl\.?\s*)?[a-zA-Z]+\.?", r"\1", text)
    # "juice of 1 lemon" -> "1 lemon"
    text = re.sub(r"^(?:the\s+)?(?:juice|zest|zest and juice|juice and zest)\s+(?:of|from)\s+", "", text, flags=re.IGNORECASE)
    # "2 x 400g tins chickpeas", "2 (400g) cans black beans"
    if m := re.match(rf"^\s*({_NUM})\s*(?:x\s*|\(\s*)(?:{_NUM})\s*\s*(?:g|ml|oz)\b\)?\s*(?:cans?|tins?|jars?)\b\s*(?:of\s+)?(.*)$",
                     text, re.IGNORECASE):
        return f"{_fmt(_number(m.group(1)))} dåse {translate_name(m.group(2))}".strip()
    # Står der en metrisk mængde i parentes, bruges den: "1 cup (240ml) milk", "2 lb (900g) potatoes"
    metric = re.search(rf"\(\s*(?:about\s+|approx\.?\s+)?({_NUM})\s*(g|kg|ml|l)\b[^)]*\)", text, re.IGNORECASE)
    m = re.match(rf"^\s*(?:about\s+|approx\.?\s+)?({_NUM})(?:\s*-\s*({_NUM}))?\s*(?:x\s*)?([a-zA-Z]+\.?)?(?=\s|$|\()\s*(.*)$",
                 text)
    if not m:
        return translate_name(text)
    amount = _number(m.group(1))
    if m.group(2):
        amount = (amount + _number(m.group(2))) / 2
    unit = (m.group(3) or "").lower().rstrip(".")
    rest = m.group(4)
    # "400g can chopped tomatoes", "2 x 400g tins of chickpeas"
    can = re.match(r"^\(?\s*(?:can|cans|tin|tins|jar|jars)\b\s*(?:of\s+)?(.*)", rest, re.IGNORECASE)
    if unit in ("g", "ml", "oz") and can:
        count = 1
        multi = re.match(rf"^\s*({_NUM})\s*x\s*", text)
        if multi:
            count = _number(multi.group(1))
        return f"{_fmt(count)} dåse {translate_name(can.group(1))}".strip()
    if metric and unit in ("cup", "cups", "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "c"):
        amount, unit = _number(metric.group(1)), metric.group(2).lower()
        rest = re.sub(r"\([^)]*\)", " ", rest)
    if unit in UNITS:
        da, factor = UNITS[unit]
        name = translate_name(rest)
        if unit in _NOUN_UNITS:
            # "2 chicken breasts": enheden er en del af varen; "1 large onion", "1 unit onion": ikke
            part_of_name = unit in ("fillet", "fillets", "breast", "breasts", "thigh", "thighs")
            name = translate_name(f"{unit} {rest}") if part_of_name else name
            return f"{_fmt(amount)} {name}".strip()
        if da == "dl" and factor != 1 or da == "g" and factor != 1:
            amount *= factor
        if da == "ml" and factor != 1:
            amount *= factor
        if da == "ml" and amount >= 100:
            amount, da = amount / 100, "dl"
        if da == "fed" and not name.startswith("hvidløg"):
            name = name.replace("fed hvidløg", "hvidløg") or "hvidløg"
        return f"{_fmt(amount)} {da} {name}".strip()
    return f"{_fmt(amount)} {translate_name(f'{unit} {rest}')}".strip()


_DANISH_WORDS = {w for v in WORDS.values() for w in v.split()}


def _english_meat_left(text: str) -> str:
    """Et engelsk kød- eller fiskeord, der ikke blev oversat ("bacon" er også dansk)."""
    words = [w for w in re.findall(r"[a-zæøå]+", text.lower()) if w not in _DANISH_WORDS]
    for w in words:
        if any(w == m or (w.startswith(m) and len(m) >= 4) or w == m + "s" for m in ENGLISH_MEAT):
            return w
    return ""


def _compound(first: str, second: str) -> str:
    """ "kylling" + "suppe" -> "kyllingesuppe"."""
    joins = {"kylling": "kyllinge", "okse": "okse", "lam": "lamme", "laks": "lakse", "fisk": "fiske", "reje": "reje",
             "rejer": "reje", "tomat": "tomat", "kartoffel": "kartoffel", "linse": "linse", "bønne": "bønne",
             "champignon": "champignon", "grøntsags": "grøntsags", "kalkun": "kalkun", "svinekød": "svine",
             "pølse": "pølse", "torsk": "torske", "tun": "tun", "kikærte": "kikærte", "græskar": "græskar",
             "blomkål": "blomkåls", "spinat": "spinat", "porre": "porre", "ærte": "ærte", "kokos": "kokos",
             "jordnødde": "jordnødde", "and": "ande", "skinke": "skinke", "chili": "chili", "hvidløg": "hvidløgs",
             "citron": "citron", "ingefær": "ingefær", "honning": "honning", "sennep": "sennep", "ost": "oste"}
    seconds = {"suppe", "gryde", "gryderet", "karry", "salat", "tærte", "burger", "burgere", "kødboller", "spyd",
               "wok", "gratin", "pasta", "frikadeller", "bøffer", "ris", "nudler", "sauce", "smør", "risotto",
               "lasagne", "mos", "bryst", "lår", "vinger", "filet", "fileter", "skulder", "kam", "koteletter", "bøf"}
    if first in joins and second in seconds:
        return joins[first] + second
    return ""


# Udtryk, der oversættes samlet, før ordene
_TITLE_PHRASES = {
    "leg of lamb": "lammekølle", "cream of": "cremet", "leftover": "", "leftovers": "", "instant pot": "trykkoger", "air fryer": "airfryer", "air-fryer": "airfryer",
    "slow cooker": "slow-cooker", "slow-cooker": "slow-cooker", "sheet pan": "bradepande", "sheet-pan": "bradepande",
    "pot pie": "tærte", "fish and chips": "fish and chips", "bangers and mash": "pølser med kartoffelmos",
    "toad in the hole": "toad in the hole", "toad-in-the-hole": "toad in the hole", "mac and cheese": "mac and cheese",
    "mac 'n' cheese": "mac and cheese", "cheat's": "", "shepherd's pie": "shepherd's pie", "cottage pie": "cottage pie",
    "sweet potato": "sød kartoffel", "sweet potatoes": "søde kartofler", "spring onion": "forårsløg",
    "spring onions": "forårsløg", "green beans": "grønne bønner", "black beans": "sorte bønner",
    "butter beans": "smørbønner", "kidney beans": "kidneybønner", "cherry tomato": "cherrytomat",
    "cherry tomatoes": "cherrytomater", "pork belly": "flæskesteg", "pork chops": "koteletter",
    "pork tenderloin": "svinemørbrad", "pork loin": "svinekam", "chicken breast": "kyllingebryst",
    "chicken breasts": "kyllingebryst", "chicken thighs": "kyllingelår", "chicken thigh": "kyllingelår",
    "chicken wings": "kyllingevinger", "chicken legs": "kyllingelår", "chicken drumsticks": "kyllingeunderlår",
    "duck breast": "andebryst", "salmon fillet": "laksefilet", "salmon fillets": "laksefilet", "fish pie": "fisketærte",
    "fish cakes": "fiskefrikadeller", "fishcakes": "fiskefrikadeller", "fish fingers": "fiskefingre",
    "meat sauce": "kødsauce", "mashed potatoes": "kartoffelmos", "mashed potato": "kartoffelmos", "mash": "mos",
    "fried rice": "stegte ris", "egg fried rice": "stegte ris med æg", "stir fry": "wok", "stir-fry": "wok",
    "stir-fried": "wokket", "one pot": "one-pot", "one-pot": "one-pot", "one pan": "one-pan", "one-pan": "one-pan",
    "bell pepper": "peberfrugt", "bell peppers": "peberfrugter", "red pepper": "rød peberfrugt",
    "red peppers": "røde peberfrugter", "garlic butter": "hvidløgssmør", "black bean": "sorte bønner", "white bean": "hvide bønner",
    "broad bean": "bondebønner", "broad beans": "bondebønner", "green bean": "grønne bønner", "garlic bread": "hvidløgsbrød",
    "herb butter": "kryddersmør", "chilli con carne": "chili con carne", "chili con carne": "chili con carne", "pasta bake": "pasta i fad", "rice bake": "ris i fad",
}
_SUFFIXES = {"i én gryde", "på én pande", "i fad", "på pande", "i trykkoger", "i airfryer", "på bradepande"}
# Retten selv: på engelsk står den sidst, efter hvad den er lavet af
_HEADS = {"suppe", "gryde", "gryderet", "karry", "salat", "tærte", "tærter", "burger", "burgere", "wok", "ris",
          "nudler", "pasta", "risotto", "lasagne", "gratin", "spyd", "tacos", "wraps", "wrap", "frikadeller", "bøffer",
          "skål", "skåle", "chili", "kødboller", "spaghetti", "penne", "pizza", "quiche", "omelet", "frittata",
          "sandwich", "fladbrød", "pakker", "bidder", "hash", "mos", "stegte ris", "orzo", "gnocchi", "linguine",
          "tagliatelle", "rigatoni", "makaroni", "couscous", "kyllingelår", "kyllingebryst", "kyllingeunderlår",
          "kylling", "laks", "laksefilet", "torsk", "koteletter", "pølser", "bøf", "fiskefrikadeller",
          "kyllingevinger", "andebryst", "lammekølle", "mørbrad", "flæskesteg"}
# Ord, der beskriver retten og bliver stående foran den
_ADJ = {"nem", "hurtig", "klassisk", "sund", "sundere", "hjemmelavet", "cremet", "sprød", "stærk", "klistret", "røget",
        "ovnstegt", "ovnbagt", "bagt", "grillet", "stegt", "pandestegt", "fyldt", "langtidsstegt", "langtidskogt",
        "braiseret", "pulled", "vegetar", "vegansk", "mexicansk", "italiensk", "thai", "indisk", "kinesisk", "japansk",
        "koreansk", "græsk", "marokkansk", "spansk", "fransk", "vietnamesisk", "mellemøstlig", "middelhavs",
        "asiatisk", "cajun", "lettere", "let", "stor", "mini", "sød", "sur", "grøn", "rød", "sort", "hvid", "brun",
        "sommer", "vinter", "efterårs", "forårs", "familie", "hurtige"}
_ADJ |= {"lun", "gylden", "dampet", "sauteret", "glaseret", "paneret", "revet", "smadrede", "blandet", "kogt",
         "toppet", "syltet", "smøret", "frisk", "syrlig", "fyldig", "mættende", "grov", "rustik", "mager", "proteinrig",
         "glutenfri", "mælkefri", "billig", "hverdags", "langtids", "wokket", "halv", "hel", "amerikansk", "britisk",
         "engelsk", "irsk", "skotsk", "cubansk", "caribisk", "hawaiiansk", "persisk", "libanesisk", "tyrkisk",
         "portugisisk", "tysk", "svensk", "nordisk", "toscansk", "provencalsk", "malaysisk", "indonesisk",
         "filippinsk", "peruviansk", "brasiliansk", "etiopisk", "afrikansk", "siciliansk", "tex-mex", "keto", "paleo",
         "rester", "minutters", "ovnbagt", "saltet"}
# Ental -> flertal efter "med": "Chili med bønner"
_PLURAL = {"grøntsags": "grøntsager", "nudel": "nudler", "bønne": "bønner", "reje": "rejer", "linse": "linser", "kikærte": "kikærter", "ærte": "ærter",
           "tomat": "tomater", "pølse": "pølser", "krydderurte": "krydderurter", "jordnødde": "jordnødder",
           "kartoffel": "kartofler", "gulerod": "gulerødder", "porre": "porrer", "okse": "oksekød", "svinekød": "svinekød",
           "lam": "lam", "and": "and", "ost": "ost"}
_PREPOSITIONS = {"med", "i", "på", "til", "eller"}


def _join_compounds(words: list[str]) -> list[str]:
    joined: list[str] = []
    for w in words:
        if joined and (c := _compound(joined[-1], w)):
            joined[-1] = c
        else:
            joined.append(w)
    return joined


def _danish_order(out: list[str]) -> str:
    """ "Røget bønne chili" -> "Røget chili med bønner", "kylling og porre tærte" -> "tærte med kylling og porre"."""
    phrases = [w for w in out if w]
    suffix = [w for w in phrases if w in _SUFFIXES]
    phrases = [w for w in phrases if w not in _SUFFIXES]
    # Retten er det sidste retnavn før første "med": "Salvie koteletter med pasta"
    cut = next((i for i, w in enumerate(phrases) if w in _PREPOSITIONS), len(phrases))
    head_at = max((i for i, w in enumerate(phrases[:cut]) if w in _HEADS), default=-1)
    before, head, after = phrases[:head_at], phrases[head_at:head_at + 1], phrases[head_at + 1:]
    if head_at <= 0 or any(w in _PREPOSITIONS for w in before):
        return " ".join(_join_compounds(" ".join(phrases + suffix).split()))
    adjs = [w for w in before if w in _ADJ or w.startswith("\x00")]
    mods = [w for w in before if w not in adjs and w != "og"]
    if not mods:
        words = adjs + head
    elif len(mods) == 1 and len(mods[0].split()) == 1 and _compound(mods[0], head[0]):
        words = adjs + [_compound(mods[0], head[0])]
    else:
        listed = [_PLURAL.get(m, m) for m in mods]
        listed = listed[0] if len(listed) == 1 else ", ".join(listed[:-1]) + " og " + listed[-1]
        words = adjs + head + ["med", listed]
    words = " ".join(words + _join_compounds(" ".join(after).split()) + suffix).split()
    # Kun ét "med": "Koteletter med salvie og grøntsagspasta"
    first = words.index("med") if "med" in words else len(words)
    return " ".join(w if w != "med" or i == first else "og" for i, w in enumerate(words))


def translate_title(name: str) -> str | None:
    """Opskriftens navn på dansk, eller None hvis et ord ikke kan oversættes."""
    text = _clean(name)
    text = re.sub(r"\s*[|:-]\s*(recipe|recipes)\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\brecipes?\b", "", text, flags=re.IGNORECASE)
    # "Jools' tuna pasta bake", "Gary Rhodes' chicken stew", "Dad's soup"
    owner = re.match(r"^((?:[A-Z][\w.-]*\s+){0,2}[A-Z][\w.-]*)['’]s?\s+", text)
    if owner and not any(w.lower() in TITLE_WORDS or w.lower() in WORDS for w in owner.group(1).split()):
        text = text[owner.end():]
    text = re.sub(r"^(?:video recipe!|sponsored:)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+[- ]minutes?\b|\b\d+[- ]ingredients?\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\([^)]*\)", " ", text)
    done: list[str] = []  # udtryk, der allerede er oversat, står som §0, §1 ...

    def mark(m: re.Match) -> str:
        done.append(_TITLE_PHRASES[m.group(0).lower()])
        return f" §{len(done) - 1} "
    phrases = sorted(_TITLE_PHRASES, key=len, reverse=True)
    text = re.sub(r"(?<![\w-])(?:" + "|".join(re.escape(p) for p in phrases) + r")(?![\w-])", mark, text,
                  flags=re.IGNORECASE)
    tokens = re.findall(r"§\d+|[\w'’-]+|&", text)
    if not tokens:
        return None
    out: list[str] = []
    i = 0
    while i < len(tokens):
        # To ord ad gangen først: "fried rice", "fish cakes", "sweet potato"
        pair = f"{tokens[i]} {tokens[i + 1]}".lower() if i + 1 < len(tokens) and "§" not in tokens[i] + tokens[i + 1] else ""
        if pair and (pair in TITLE_WORDS or pair in WORDS):
            out.append(TITLE_WORDS.get(pair) or WORDS[pair])
            i += 2
            continue
        w = tokens[i].lower()
        if w.startswith("§"):
            out.append(TITLE_WORDS.get(done[int(w[1:])], done[int(w[1:])]))
        elif w in TITLE_WORDS:
            out.append(TITLE_WORDS[w])
        elif w in WORDS:
            out.append(WORDS[w])
        elif w in DISHES or w.rstrip("s") in DISHES:
            # Flere retnavne i træk er ét navn: "lo mein", "tikka masala"
            if out and out[-1].startswith("\x00"):
                out[-1] += " " + w
            else:
                out.append("\x00" + w)
        elif re.fullmatch(r"\d+(-\w+)?", w):
            out.append(w)
        else:
            return None
        i += 1
    title = _danish_order(out).replace("\x00", "")
    title = re.sub(r"\b(med|og|i|på|til)( (med|og|i|på|til))+\b", r"\1", title).strip()
    title = re.sub(r"^(med|og|i|på|til) |( med| og| i| på| til)$", "", title).strip()
    return title[:1].upper() + title[1:] if title else None


def translate_category(category: str) -> str:
    text = category.lower()
    for en, da in sorted(CATEGORY_WORDS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{re.escape(en)}\b", da, text)
    return text


def is_english(page: str) -> bool:
    """Er siden på engelsk? Ud fra <html lang="en-GB"> eller inLanguage."""
    m = re.search(r"<html\b[^>]*\blang\s*=\s*[\"']?([a-zA-Z]{2})", page, re.IGNORECASE)
    if m:
        return m.group(1).lower() == "en"
    m = re.search(r'"inLanguage"\s*:\s*"([a-zA-Z]{2})', page)
    return bool(m and m.group(1).lower() == "en")


def danish(recipe: dict) -> tuple[dict | None, str]:
    """En hentet engelsk opskrift på dansk, eller (None, grund).

    Danske opskrifter gives tilbage uændret.
    """
    if recipe.get("lang") != "en":
        return recipe, ""
    name = recipe["name"]
    if any(re.search(rf"\b{re.escape(w)}\b", name.lower()) for w in NOT_DINNER_EN):
        return None, "ikke aftensmad"
    title = translate_title(name)
    if not title:
        return None, f"navnet kunne ikke oversættes: {name}"
    lines = []
    for line in recipe["ingredients"]:
        da = translate_line(line)
        if (left := _english_meat_left(da)):
            return None, f"ukendt kød eller fisk: {left}"
        lines.append(da)
    return {**recipe, "name": title, "category": translate_category(recipe.get("category", "")),
            "ingredients": lines}, ""
