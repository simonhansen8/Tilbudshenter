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
