import json
from datetime import timedelta

from tilbudshenter.cli import main
from tilbudshenter.pages import STATIC_MARKER, site_config
from tilbudshenter.scanner import scan
from tilbudshenter.sources.demo import DemoSource

from conftest import NOW


def test_site_demo(tmp_path, capsys):
    out = tmp_path / "side"
    assert main(["side", "--demo", "--ud", str(out)]) == 0
    assert "Siden er bygget" in capsys.readouterr().out

    html = (out / "index.html").read_text("utf-8")
    assert html.count(STATIC_MARKER) == 1 and html.index(STATIC_MARKER) < html.index("const STATIC")
    data = json.loads((out / "data.json").read_text("utf-8"))
    assert data["last_scan"] and data["catalog_count"] > 0
    assert data["offers"] and all("price_text" in o and "category_name" in o for o in data["offers"])
    # Alle kategorier sendes med; brugerens valg anvendes i browseren
    assert {"koed", "oel_og_vin"} <= {o["category"] for o in data["offers"]}
    assert {s["name"] for s in data["stores"]} >= {"Netto", "Lidl"}
    assert data["default_settings"]["stores"] and data["default_settings"]["categories"]
    assert (out / "tilbud.demo.db").exists()

    # Anden kørsel genbruger databasen og henter ikke aviserne igen
    assert main(["side", "--demo", "--ud", str(out)]) == 0
    assert "0 nye aviser" in capsys.readouterr().out


def test_site_config_keeps_user_filters_out():
    cfg = site_config()
    assert "Netto" in cfg.stores and not cfg.categories and not cfg.favorites


def test_prune(cfg, categorizer, storage):
    scan(cfg, DemoSource(now=NOW), storage, categorizer, now=NOW)
    assert storage.prune(NOW - timedelta(days=1)) == 0
    assert storage.prune(NOW + timedelta(days=30)) > 0
    assert not storage.current_offers(NOW) and not storage.catalogs()
