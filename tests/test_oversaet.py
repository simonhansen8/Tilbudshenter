from tilbudshenter.mealplan import line_keys, parse_line, recipe_from_lines
from tilbudshenter.opskrifter import is_dinner
from tilbudshenter.oversaet import danish, is_english, translate_line, translate_title


def test_translate_line_units():
    assert translate_line("1 cup (240ml) whole milk") == "2,4 dl sødmælk"
    assert translate_line("1 ½ cups long grain rice") == "3,6 dl ris"
    assert translate_line("1 lb ground beef") == "455 g hakket oksekød"
    assert translate_line("8 oz spaghetti") == "225 g spaghetti"
    assert translate_line("2 lbs (900g) potatoes") == "900 g kartofler"
    assert translate_line("2 tbsp olive oil") == "2 spsk olivenolie"
    assert translate_line("1/2 tsp chilli flakes") == "0,5 tsk chiliflager"
    assert translate_line("250ml/9fl oz vegetable stock") == "2,5 dl grøntsagsbouillon"
    assert translate_line("3 garlic cloves, crushed") == "3 fed hvidløg"
    assert translate_line("1 unit(s) Onion") == "1 løg"
    assert translate_line("1 large onion, finely chopped") == "1 løg"
    assert translate_line("2 boneless, skinless chicken breasts") == "2 kyllingebryst"
    assert translate_line("juice of ½ a lemon") == "0,5 citron"
    assert translate_line("For the sauce") == ""
    # Ordet til sidst gælder begge muligheder: bouillon er ikke kylling
    assert translate_line("90ml chicken or vegetable stock") == "90 ml hønsebouillon"
    assert translate_line("2 chicken or turkey breasts") == "2 kyllingebryst"
    assert translate_line("75ml apple juice") == "75 ml æblejuice"
    assert translate_line("4 tbsp tomato ketchup") == "4 spsk ketchup"
    assert translate_line("8–10 sheets of dried egg lasagne") == "9 tørret lasagneplader"


def test_translate_line_cans():
    assert translate_line("400g can chopped tomatoes") == "1 dåse hakkede tomater"
    assert translate_line("2 x 400g tins chickpeas, drained") == "2 dåse kikærter"
    assert translate_line("2 (15 oz) cans black beans, rinsed") == "2 dåse sorte bønner"
    assert translate_line("1 can (14 oz) coconut milk") == "1 dåse kokosmælk"


def test_translated_lines_match_offers():
    # De oversatte linjer skal kunne findes i tilbudsaviserne
    for line, key in [("500g beef mince", "hakket_okse"), ("4 chicken thighs (skin-on)", "kyllingelaar"),
                      ("200ml double cream", "floede"), ("1 red pepper, sliced", "peberfrugt"),
                      ("400g can chopped tomatoes", "hakkede_tomater"), ("300g basmati rice", "ris"),
                      ("500g chicken thigh fillets", "kyllingelaar"), ("2 salmon fillets", "laksefilet")]:
        assert key in line_keys(parse_line(translate_line(line))[2]), line


def test_translate_title():
    assert translate_title("Chicken and leek pie") == "Tærte med kylling og porrer"
    assert translate_title("Easy beef stew") == "Nem oksegryde"
    assert translate_title("Lentil soup") == "Linsesuppe"
    assert translate_title("One-pot chicken & chorizo rice") == "Ris med kylling og chorizo i én gryde"
    assert translate_title("Sticky honey garlic chicken thighs") == "Klistret kyllingelår med honning og hvidløg"
    assert translate_title("Spaghetti carbonara") == "Spaghetti carbonara"
    assert translate_title("Leg of lamb with rosemary") == "Lammekølle med rosmarin"
    assert translate_title("Jools' tuna pasta bake") == "Tunpasta i fad"
    # Ord, ordlisten ikke kender, giver intet navn hellere end et halvt engelsk
    assert translate_title("Prawns in Longjing tea") is None


def test_danish_recipe():
    recipe = {"url": "https://www.bbcgoodfood.com/recipes/chicken-leek-pie", "lang": "en",
              "name": "Chicken and leek pie", "category": "Dinner, Main course", "persons": 4,
              "ingredients": ["500g chicken thigh fillets", "2 leeks, sliced", "200ml double cream",
                              "320g puff pastry", "1 tbsp plain flour"]}
    da, why = danish(recipe)
    assert not why and da["name"] == "Tærte med kylling og porrer" and is_dinner(da)
    assert da["ingredients"][:3] == ["500 g kyllingelårfilet", "2 porrer", "2 dl piskefløde"]
    r, why = recipe_from_lines("x", da["name"], da["ingredients"], 4)
    assert r and r.kind == "kylling"
    # Danske opskrifter er uændrede
    assert danish({"name": "Frikadeller", "ingredients": []}) == ({"name": "Frikadeller", "ingredients": []}, "")
    # Kager og kød, ordlisten ikke kender, bruges ikke
    assert danish({**recipe, "name": "Chocolate cake"})[1] == "ikke aftensmad"
    assert danish({**recipe, "ingredients": ["500g venison haunch"]})[1].startswith("ukendt kød eller fisk")


def test_is_english():
    assert is_english('<html lang="en-GB"><body>')
    assert not is_english('<html lang="da-DK">')
    assert not is_english("<html><body>")


def test_english_leftovers_and_ounces():
    from tilbudshenter.oversaet import translate_line

    assert translate_line("1 bunch English spinach") == "1 bundt spinat"
    assert translate_line("2 tbsp extra-virgin olive oil") == "2 spsk olivenolie"
    assert translate_line("1 15 oz. can diced tomatoes ($0.89)") == "1 dåse hakkede tomater"
    assert translate_line("2 15 oz cans chick peas, drained") == "2 dåse kikærter"
    assert translate_line("250 - 300 g / 8 - 10 oz pasta or egg noodles of choice") == "275 g pasta"
    assert translate_line("1lb 5oz lamb neck fillet") == "595 g lammekød"


def test_english_name_on_danish_site_is_translated():
    from tilbudshenter.oversaet import danish

    recipe = {"name": "Italian chicken rigatoni with fresh spinach and bell pepper", "ingredients": []}
    assert danish(recipe)[0]["name"] == "Italiensk rigatoni med kylling og frisk spinat og peberfrugt"
    danish_name = {"name": "Poke bowl med and, grøn chili og mango", "ingredients": []}
    assert danish(danish_name)[0]["name"] == danish_name["name"]


def test_no_english_left_in_common_lines():
    # Linjer, der før havde engelske ord tilbage i madplanen
    cases = {
        "2 tsp black peppercorns": "2 tsk sorte peberkorn",
        "1 vegetable stock cube": "1 grøntsagsbouillonterning",
        "+ 1 teaspoon sugar": "1 tsk sukker",
        "1⁄2 tsp fine sea salt": "0,5 tsk fine havsalt",
        "cayenne pepper (more to taste": "cayennepeber",
        "2 6-ounce chicken breasts": "2 kyllingebryst",
        "1/4 cup chopped fresh cilantro": "0,6 dl hakket frisk koriander",
        "200g beansprouts": "200 g bønnespirer",
        "1 knob of butter": "15 g smør",
        "4 naan breads": "4 naanbrød",
        "2 tbsp clear honey": "2 spsk honning",
        "1 x 2kg/4½lb free-range organic chicken": "1 kylling",
    }
    for line, want in cases.items():
        assert translate_line(line) == want, line


def test_unclosed_parenthesis_keeps_the_item():
    # "boneless, (skinless chicken breasts": varen står i parentesen
    assert translate_line("1½ pounds boneless, (skinless chicken breasts or tenderloins") == "680 g kyllingebryst"


def test_title_adjectives_agree_with_plural():
    assert translate_title("Baked Shrimp with Feta") == "Bagte rejer med feta"
    assert translate_title("Swedish Meatballs") == "Svenske kødboller"
    assert translate_title("Herby steak & crispy potatoes") == "Bøf med krydderurter og sprøde kartofler"
    assert translate_title("Sausage rolls") == "Pølsehorn"
    assert translate_title("Toad in the hole") == "Pølser i dej"


def test_redcurrant_jelly_is_not_meat():
    recipe = {"lang": "en", "name": "Lamb chops with potatoes", "category": "",
              "ingredients": ["4 lamb chops", "2 tbsp redcurrant jelly", "300ml chicken stock"]}
    da, why = danish(recipe)
    assert da is not None, why
