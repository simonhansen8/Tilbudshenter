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
