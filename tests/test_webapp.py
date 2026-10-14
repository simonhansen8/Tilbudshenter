import json
import threading
import time
import tomllib
import urllib.error
import urllib.request

import pytest

from tilbudshenter.config import Config, _from_dict, render_config
from tilbudshenter.webapp import App, apply_settings, make_server


def test_render_config_round_trip(tmp_path):
    cfg = Config(
        latitude=56.15, longitude=10.2, radius_km=7.5,
        stores=["Netto", "føtex"], exclude_catalogs=["legetøj", 'citat "x"'],
        categories=["koed"], max_price=99.5, only_known_discount=True,
        favorites=["skyr"], custom_categories={"morgenmad": {"navn": "Morgenmad", "noegleord": ["havregryn"]}},
        database=tmp_path / "data" / "tilbud.db", output_dir=tmp_path / "rapporter",
    )
    text = render_config(cfg, tmp_path)
    loaded = _from_dict(tomllib.loads(text))
    assert (loaded.latitude, loaded.longitude, loaded.radius_km) == (56.15, 10.2, 7.5)
    assert loaded.stores == ["Netto", "føtex"]
    assert loaded.exclude_catalogs == ["legetøj", 'citat "x"']
    assert loaded.max_price == 99.5 and loaded.only_known_discount
    assert loaded.custom_categories == {"morgenmad": {"navn": "Morgenmad", "noegleord": ["havregryn"]}}
    assert str(loaded.database) == "data/tilbud.db"


def test_apply_settings():
    cfg = apply_settings(Config(), {
        "latitude": "55.5", "stores": ["Netto", " ", "Lidl"], "max_price": "",
        "only_known_discount": True, "ukendt": 1,
    })
    assert cfg.latitude == 55.5
    assert cfg.stores == ["Netto", "Lidl"]
    assert cfg.max_price is None and cfg.only_known_discount
    with pytest.raises(ValueError):
        apply_settings(Config(), {"radius_km": 0})
    with pytest.raises(ValueError):
        apply_settings(Config(), {"stores": "Netto"})


@pytest.fixture
def server(tmp_path):
    app = App(tmp_path / "tilbudshenter.toml", demo=True)
    srv = make_server(app, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def request(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read() or b"null") if "json" in res.headers["Content-Type"] else res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_server_scan_and_settings(server, tmp_path):
    status, page = request(server + "/")
    assert status == 200 and b"Tilbudshenter" in page

    status, state = request(server + "/api/state")
    assert state["demo"] and state["last_scan"] is None
    assert (tmp_path / "tilbudshenter.toml").exists()

    # Ændringer kræver appens header
    assert request(server + "/api/scan", {})[0] == 403
    assert request(server + "/api/scan", {}, {"X-Tilbudshenter": "1"})[0] == 200
    for _ in range(100):
        state = request(server + "/api/state")[1]
        if not state["scan"]["running"]:
            break
        time.sleep(0.05)
    assert state["scan"]["result"]["new_catalogs"] > 0

    offers = request(server + "/api/offers")[1]["offers"]
    assert offers and {"price_text", "category_name", "known_discount"} <= offers[0].keys()

    stores = request(server + "/api/catalogs")[1]["stores"]
    assert any(s["name"] == "Netto" for s in stores)

    status, _ = request(server + "/api/settings", {"stores": ["Netto"]}, {"X-Tilbudshenter": "1"})
    assert status == 200
    assert {o["dealer"] for o in request(server + "/api/offers")[1]["offers"]} == {"Netto"}
    assert request(server + "/api/settings", {"radius_km": -1}, {"X-Tilbudshenter": "1"})[0] == 400


def test_server_rejects_foreign_host(server):
    status, body = request(server + "/api/state", headers={"Host": "evil.example"})
    assert status == 403


def test_old_config_gets_new_stores_once(tmp_path):
    from tilbudshenter.cli import load_app_config
    from tilbudshenter.config import save_config

    path = tmp_path / "tilbudshenter.toml"
    save_config(Config(stores=["Netto", "kvickly"], exclude_stores=["SPAR"]), path)
    cfg = load_app_config(path, demo=False)
    assert cfg.stores == ["Netto", "kvickly", "SuperBrugsen", "Brugsen", "MENY"]
    assert "SuperBrugsen" in path.read_text(encoding="utf-8")

    # Fravælger brugeren en af dem bagefter, kommer den ikke igen
    cfg.stores = ["Netto", "kvickly"]
    save_config(cfg, path)
    assert load_app_config(path, demo=False).stores == ["Netto", "kvickly"]


def test_all_stores_and_new_config_not_changed(tmp_path):
    from tilbudshenter.cli import load_app_config
    from tilbudshenter.config import example_config, save_config

    path = tmp_path / "alle.toml"
    save_config(Config(stores=[]), path)
    assert load_app_config(path, demo=False).stores == []

    path = tmp_path / "ny.toml"
    save_config(example_config(), path)
    before = path.read_text(encoding="utf-8")
    load_app_config(path, demo=False)
    assert path.read_text(encoding="utf-8") == before


def test_shopping_list(server):
    h = {"X-Tilbudshenter": "1"}
    assert request(server + "/api/scan", {}, h)[0] == 200
    for _ in range(100):
        if not request(server + "/api/state")[1]["scan"]["running"]:
            break
        time.sleep(0.05)
    offer = request(server + "/api/offers")[1]["offers"][0]

    status, data = request(server + "/api/list", {"action": "add", "id": offer["id"]}, h)
    assert status == 200 and [i["id"] for i in data["items"]] == [offer["id"]]
    item = data["items"][0]
    assert item["dealer"] == offer["dealer"] and item["price_text"] == offer["price_text"]

    # Samme tilbud to gange giver kun én linje; egne varer kan tilføjes
    request(server + "/api/list", {"action": "add", "id": offer["id"]}, h)
    data = request(server + "/api/list", {"action": "add_text", "text": "Mælk"}, h)[1]
    assert [i["heading"] for i in data["items"]] == [offer["heading"], "Mælk"]

    data = request(server + "/api/list", {"action": "check", "id": offer["id"], "checked": True}, h)[1]
    assert data["items"][0]["checked"]
    data = request(server + "/api/list", {"action": "clear", "only_checked": True}, h)[1]
    assert [i["heading"] for i in data["items"]] == ["Mælk"]

    assert request(server + "/api/list", {"action": "add", "id": "findes-ikke"}, h)[0] == 400
    assert request(server + "/api/list", {"action": "clear"})[0] == 403
    assert request(server + "/api/list", {"action": "clear"}, h)[1]["items"] == []


def test_recipes(server):
    status, data = request(server + "/api/recipes")
    assert status == 200 and data["recipes"] and data["recipes"][0]["items"]
    assert data["ingredients"] and data["side"]


def test_list_notes_and_departments(server):
    h = {"X-Tilbudshenter": "1"}
    request(server + "/api/scan", {}, h)
    for _ in range(100):
        if not request(server + "/api/state")[1]["scan"]["running"]:
            break
        time.sleep(0.05)
    offer = request(server + "/api/offers")[1]["offers"][0]
    request(server + "/api/list", {"action": "add", "id": offer["id"], "note": "til Lasagne"}, h)
    items = request(server + "/api/list", {"action": "add_text", "text": "Løg (3)", "category": "frugt_og_groent",
                                           "note": "til Chili"}, h)[1]["items"]
    by_id = {i["id"]: i for i in items}
    assert by_id[offer["id"]]["note"] == "til Lasagne" and by_id[offer["id"]]["category"] == offer["category"]
    own = next(i for i in items if i["heading"] == "Løg (3)")
    assert own["note"] == "til Chili" and own["category"] == "frugt_og_groent"


def test_old_shopping_list_gets_new_columns(tmp_path):
    import sqlite3

    from tilbudshenter.storage import Storage

    db = tmp_path / "gammel.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE shopping_list (id TEXT PRIMARY KEY, dealer TEXT, heading TEXT NOT NULL, "
                 "description TEXT, price REAL, unit TEXT, amount REAL, run_from TEXT, run_till TEXT, "
                 "added_at TEXT NOT NULL, checked INTEGER NOT NULL DEFAULT 0)")
    conn.commit()
    conn.close()
    with Storage(db) as storage:
        storage.add_text_to_list("Mælk", note="til grød")
        assert storage.shopping_list()[0]["note"] == "til grød"


def test_import_recipe(server, monkeypatch):
    from tests.test_opskrifter import PAGE

    monkeypatch.setattr("tilbudshenter.webapp.fetch", lambda url: PAGE)
    h = {"X-Tilbudshenter": "1"}
    status, data = request(server + "/api/import_recipe", {"url": "https://mad.dk/chili"}, h)
    assert status == 200 and data["recipe"]["name"] == "Chili con carne & ris"
    assert data["recipe"]["method"].startswith("Brun kødet")
    assert request(server + "/api/import_recipe", {"url": "file:///etc/passwd"}, h)[0] == 400
    monkeypatch.setattr("tilbudshenter.webapp.fetch", lambda url: "<html></html>")
    assert request(server + "/api/import_recipe", {"url": "https://mad.dk/"}, h)[0] == 400
