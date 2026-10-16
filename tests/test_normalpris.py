"""Normalpris ved tilbuddene: butikkens egen fra avisen, ellers basisprisen.

JavaScript-delen (mellem "// <normalpris>" og "// </normalpris>" i app.html)
køres i Node.
"""

import json
import re
import shutil
import subprocess
from importlib import resources

import pytest

from tilbudshenter.categories import Categorizer
from tilbudshenter.mealplan import offer_basis_key, plan_payload
from tilbudshenter.models import Offer
from tilbudshenter.webapp import offer_payload


@pytest.mark.parametrize("heading, unit, key", [
    ("Netto hakket oksekød 8-12%", "kg", "hakket_okse"),
    ("Arla letmælk", "l", "maelk"),
    ("COMBINO Spaghetti", "kg", "pasta"),
    ("Agurk", "stk", "agurk"),
    ("Tulip bacon", "kg", "bacon"),
    # Ikke samme vare som basisvaren
    ("3-STJERNET Kartoffel- eller landspegepølse", "kg", None),
    ("Änglamark økologiske brune champignoner", "kg", None),
    ("Bacon eller hamburgerryg", "kg", None),
    # Stykpris kan kun sammenlignes for varer, der sælges pr. stk.
    ("Tulip bacon", "stk", None),
    ("Netto hakket oksekød 8-12%", None, None),
])
def test_offer_basis_key(heading, unit, key):
    assert offer_basis_key(heading, unit) == key


def _offer(heading, price, description="", pre_price=None):
    return Offer(id="x", catalog_id="c", dealer="Netto", heading=heading, price=price,
                 description=description, pre_price=pre_price)


def test_payload_has_basis_key_only_without_store_price():
    cat = Categorizer()
    assert offer_payload(_offer("Netto hakket oksekød", 35, "400 g"), cat)["basis_key"] == "hakket_okse"
    assert "basis_key" not in offer_payload(_offer("Netto hakket oksekød", 35, "400 g", pre_price=45), cat)
    assert "basis_key" not in offer_payload(_offer("Sodavand", 10, "1,5 l"), cat)


def run_js(code: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <normalpris>", 1)[1].split("// </normalpris>", 1)[0]
    money = re.search(r"^function money\(.*$", html, re.MULTILINE)[0]
    script = (f"let planData = {json.dumps(plan_payload(), ensure_ascii=False)};\n"
              "let ING = Object.fromEntries(planData.ingredients.map(i => [i.key, i]));\n"
              f"{money}\n{block}\nconsole.log(JSON.stringify({code}));\n")
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def normal(**offer):
    return run_js(f"normalPrice({json.dumps(offer)})")


def test_store_price_from_the_paper():
    n = normal(price=3.98, pre_price=13.98)
    assert (n["kind"], n["cheaper"]) == ("store", True)
    assert n["short"] == "Normalpris 13,98 kr · spar 10,00 kr"
    assert "72 %" in n["long"]


def test_store_price_not_cheaper():
    n = normal(price=20, pre_price=20)
    assert (n["kind"], n["cheaper"]) == ("store", False)
    assert n["short"].endswith("ikke billigere")


def test_basis_price_per_kg():
    basis = plan_payload()["ingredients"]
    okse = next(i for i in basis if i["key"] == "hakket_okse")["price"][0]
    n = normal(price=35, unit="kg", unit_price=okse * 0.8, basis_key="hakket_okse")
    assert (n["kind"], n["cheaper"]) == ("basis", True)
    assert n["short"] == f"Basispris ca. {okse:.2f}".replace(".", ",").replace("ca,", "ca.") + " kr/kg · 20 % billigere"
    assert "hakket oksekød" in n["long"]


def test_basis_price_more_expensive():
    n = normal(price=45, unit="kg", unit_price=200, basis_key="bacon")
    assert (n["kind"], n["cheaper"]) == ("basis", False)
    assert "dyrere" in n["short"]


def test_basis_price_per_piece():
    agurk = next(i for i in plan_payload()["ingredients"] if i["key"] == "agurk")["price"]
    n = normal(price=6, unit="stk", unit_price=6, basis_key="agurk")
    piece = agurk[0] * agurk[1] / 1000
    assert n["short"].startswith(f"Basispris ca. {piece:.2f}".replace(".", ",").replace("ca,", "ca.") + " kr/stk")


@pytest.mark.parametrize("unit_price", [3, 2000])
def test_far_from_basis_is_not_the_same_product(unit_price):
    # Fx hakkede tomater på dåse mod friske tomater, eller frugtspaghetti
    n = normal(price=10, unit="kg", unit_price=unit_price, basis_key="tomater")
    assert n["kind"] is None and n["short"] == "Normalpris ukendt"


def test_unknown():
    n = normal(price=10, unit="l", unit_price=6.67)
    assert n["kind"] is None and n["cheaper"] is None
