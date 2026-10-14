import json
from datetime import timedelta

from tilbudshenter.cli import main
from tilbudshenter.models import Catalog
from tilbudshenter.pages import (
    SCAN_POINTS, STATIC_MARKER, CountrySource, places_from_stores, site_config, static_html,
)
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


def test_places_from_stores():
    stores = {
        "Netto": [
            {"latitude": 56.15, "longitude": 10.20, "zip_code": "8000", "city": "Aarhus C"},
            {"latitude": 56.17, "longitude": 10.22, "zip_code": "8000", "city": "Aarhus C"},
            {"latitude": 55.0, "longitude": 9.0, "zip_code": "", "city": "Ukendt"},
        ],
        "Lidl": [{"latitude": 55.68, "longitude": 12.57, "zip_code": "1100", "city": "København K"}],
    }
    assert places_from_stores(stores) == [["1100", "København K", 55.68, 12.57], ["8000", "Aarhus C", 56.16, 10.21]]


def test_country_source_scans_all_points_and_fetches_stores():
    class Fake:
        name = "fake"
        points = []

        def list_catalogs(self, lat, lng, radius):
            self.points.append((lat, lng))
            return [Catalog(id="1", dealer="Netto", label="Uge", run_from=None, run_till=None, dealer_id="n"),
                    Catalog(id="2", dealer="JYSK", label="Bolig", run_from=None, run_till=None, dealer_id="j")]

        def list_stores(self, dealer_id):
            return [{"latitude": 1.0, "longitude": 2.0, "zip_code": "8000", "city": "Aarhus C"}]

    fake = Fake()
    country = CountrySource(fake)
    assert [c.id for c in country.list_catalogs(0, 0, 0)] == ["1", "2"]
    assert len(fake.points) == len(SCAN_POINTS)
    # Kun de kæder, siden viser
    assert list(country.store_locations(site_config())) == ["Netto"]


def test_saved_choices_survive_new_versions():
    # Gemte valg i browseren må ikke gå tabt, når siden opdateres: samme
    # nøgler, og de gemte valg lægges oven på standardvalgene
    html = static_html()
    assert 'localStorage.getItem("tilbudshenter." + key)' in html
    assert 'store.get("settings", {})' in html and 'store.get("list", [])' in html
    assert '{...siteData.default_settings, ...store.get("settings", {})}' in html
