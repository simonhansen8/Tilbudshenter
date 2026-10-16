"""Notifikationer om varer på tilbud bruger sidens søgning og giver kun
besked én gang pr. tilbud."""

import json
import shutil
from pathlib import Path

import pytest

from tilbudshenter.notifikation import match_offers, message, notify, read_watchlist

DATA = Path(__file__).parent / "data"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node er ikke installeret")


def offer(id, heading, dealer="Netto", category="kolonial", price=10.0, description=""):
    return {"id": id, "heading": heading, "description": description, "dealer": dealer, "category": category,
            "price": price, "price_text": f"{price:.2f} kr".replace(".", ","), "discount_text": "-25%",
            "period_text": "17/10-23/10"}


OFFERS = [
    offer("1", "Peter Larsen Kaffe", category="kaffe_og_te", price=39.95),
    offer("2", "Lavazza kaffebønner", dealer="Lidl", category="kaffe_og_te", price=99.0),
    offer("3", "Kidneybønner", price=6.0),
    offer("4", "Bananer", category="frugt", price=12.0),
    offer("5", "Is med smag af banan", category="frost", price=25.0),
    offer("6", "Pålæg", category="koed"),
    offer("7", "Skrabeæg", category="mejeri", price=22.0),
]


def test_watchlist(tmp_path):
    p = tmp_path / "liste.txt"
    p.write_text("# kommentar\nkaffe\n\nKaffe\næg  # morgenmad\nbutikker: Netto, rema 1000\n", encoding="utf-8")
    assert read_watchlist(p) == (["kaffe", "æg"], {"netto", "rema 1000"})


def test_uses_the_search_on_the_site():
    got = match_offers(["kaffe", "banan", "æg", "bønner"], OFFERS)
    names = {t: [OFFERS[i]["heading"] for i in v] for t, v in got.items()}
    assert names == {
        "kaffe": ["Peter Larsen Kaffe", "Lavazza kaffebønner"],
        "banan": ["Bananer"],  # ikke is med smag af banan
        "æg": ["Skrabeæg"],  # ikke pålæg
        "bønner": ["Kidneybønner"],  # ikke kaffebønner
    }


def test_same_hits_as_my_basics_in_real_papers():
    """Hvert søgeord i hit-testene giver besked om netop de træf, som
    "Mine basisvarer" viser (tests/data/search_cases.json, "find")."""
    offers = json.loads((DATA / "search_offers.json").read_text(encoding="utf-8"))
    cases = json.loads((DATA / "search_cases.json").read_text(encoding="utf-8"))
    got = match_offers(list(cases), offers)
    for term, want in cases.items():
        names = {f"{' '.join(offers[i]['heading'].split())} · {offers[i]['dealer']}" for i in got[term]}
        assert names == set(want["find"]), term


def test_each_offer_is_sent_once(tmp_path):
    state = tmp_path / "notifikationer.json"
    sent = []
    data = {"offers": OFFERS}
    notify(data, ["kaffe", "chips"], None, state, sent.append)
    assert [m["title"] for m in sent] == ["Kaffe er på tilbud (2 tilbud)"]
    assert sent[0]["message"].splitlines()[0] == "Netto: Peter Larsen Kaffe 39,95 kr (-25%) 17/10-23/10"
    assert sent[0]["click"].endswith("?q=kaffe")

    # Næste kørsel: samme tilbud giver ingen ny besked, et nyt gør
    sent.clear()
    data = {"offers": OFFERS + [offer("8", "Merrild kaffe", dealer="REMA 1000", category="kaffe_og_te")]}
    notify(data, ["kaffe"], None, state, sent.append)
    assert len(sent) == 1 and sent[0]["message"] == "REMA 1000: Merrild kaffe 10,00 kr (-25%) 17/10-23/10"

    # Udløbne tilbud glemmes
    notify({"offers": OFFERS[:1]}, ["kaffe"], None, state, sent.append)
    assert json.loads(state.read_text(encoding="utf-8")) == {"sendt": {"kaffe": ["1"]}}


def test_only_chosen_stores(tmp_path):
    sent = []
    notify({"offers": OFFERS}, ["kaffe"], {"lidl"}, tmp_path / "s.json", sent.append)
    assert len(sent) == 1 and sent[0]["message"].startswith("Lidl: Lavazza")


def test_failed_send_is_tried_again(tmp_path):
    state = tmp_path / "s.json"

    def fail(msg):
        raise OSError("ingen forbindelse")

    notify({"offers": OFFERS}, ["kaffe"], None, state, fail)
    sent = []
    notify({"offers": OFFERS}, ["kaffe"], None, state, sent.append)
    assert len(sent) == 1


def test_without_topic_nothing_is_remembered(tmp_path):
    state = tmp_path / "s.json"
    got = notify({"offers": OFFERS}, ["kaffe"], None, state, None)
    assert len(got["kaffe"]) == 2 and not state.exists()


def test_long_message_is_cut():
    msg = message("mælk", [offer(str(i), f"Mælk {i}") for i in range(9)])
    assert msg["message"].splitlines()[-1] == "+ 3 flere på siden"
    assert msg["click"] == "https://simonhansen8.github.io/Tilbudshenter/?q=m%C3%A6lk"
