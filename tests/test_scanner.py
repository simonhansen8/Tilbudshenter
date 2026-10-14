from dataclasses import replace
from datetime import timedelta

from tilbudshenter.scanner import scan
from tilbudshenter.sources.demo import DemoSource

from conftest import NOW


def test_scan_only_fetches_new_catalogs(cfg, categorizer, storage):
    source = DemoSource(now=NOW)
    first = scan(cfg, source, storage, categorizer, now=NOW)
    assert len(first.new_catalogs) == 5 and first.offers_fetched > 30

    second = scan(cfg, source, storage, categorizer, now=NOW)
    assert not second.found_new and len(second.known_catalogs) == 5

    forced = scan(cfg, source, storage, categorizer, force=True, now=NOW)
    assert len(forced.new_catalogs) == 5


def test_scan_respects_store_selection(cfg, categorizer, storage):
    result = scan(replace(cfg, stores=["Netto", "Lidl"]), DemoSource(now=NOW), storage, categorizer, now=NOW)
    assert sorted(c.dealer for c in result.new_catalogs) == ["Lidl", "Netto"]
    assert {o.dealer for o in storage.current_offers(NOW)} == {"Lidl", "Netto"}


def test_expired_catalogs_skipped(cfg, categorizer, storage):
    later = NOW + timedelta(days=30)
    result = scan(cfg, DemoSource(now=NOW), storage, categorizer, now=later)
    assert not result.found_new


def test_offers_are_categorized_and_stored(cfg, categorizer, storage):
    scan(cfg, DemoSource(now=NOW), storage, categorizer, now=NOW)
    offers = {o.heading: o for o in storage.current_offers(NOW)}
    assert offers["Kyllingebryst"].category == "koed"
    assert offers["Kyllingebryst"].unit_price is not None
    assert not storage.current_offers(NOW + timedelta(days=30))


def test_typical_prices_need_two_catalogs(storage):
    from tilbudshenter.models import Catalog, Offer

    for i, price in enumerate([40, 50, 60]):
        cat = Catalog(id=f"c{i}", dealer="Netto", label="", run_from=NOW, run_till=NOW)
        storage.save_catalog(cat, "test", scanned=True)
        storage.save_offers([Offer(id=f"o{i}", catalog_id=cat.id, dealer="Netto",
                                   heading="Kaffe", description="1 kg", price=price)])
    assert storage.typical_unit_prices() == {("kaffe", "kg"): 50}
    assert storage.typical_unit_prices(exclude_catalogs={"c0", "c1"}) == {}


def test_paper_details_are_stored_and_old_catalogs_fetched_again(tmp_path, cfg, categorizer):
    import sqlite3

    from tilbudshenter.storage import Storage

    class WithPages(DemoSource):
        def list_pages(self, catalog):
            return [f"{catalog.id}-p1.webp", f"{catalog.id}-p2.webp"]

    db = tmp_path / "tilbud.db"
    with Storage(db) as storage:
        scan(cfg, WithPages(now=NOW), storage, categorizer, now=NOW)
        offers = storage.current_offers(NOW)
        assert all(o.catalog_order for o in offers)
        catalog = storage.catalogs()[0]
        assert catalog.pages == [f"{catalog.id}-p1.webp", f"{catalog.id}-p2.webp"]

    # En avis, der blev hentet før sidetal og rækkefølge kom med, hentes igen én gang
    conn = sqlite3.connect(db)
    conn.execute("UPDATE catalogs SET scan_version = NULL")
    conn.commit()
    conn.close()
    with Storage(db) as storage:
        assert len(scan(cfg, WithPages(now=NOW), storage, categorizer, now=NOW).new_catalogs) == 5
        assert not scan(cfg, WithPages(now=NOW), storage, categorizer, now=NOW).found_new


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    from tilbudshenter.storage import SCHEMA, Storage

    db = tmp_path / "gammel.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)  # Tabellerne, som de så ud før
    conn.execute("INSERT INTO catalogs (id, source, dealer, first_seen, scanned_at) VALUES ('c', 'tjek', 'Netto', 'x', 'y')")
    conn.commit()
    conn.close()
    with Storage(db) as storage:
        assert not storage.is_scanned("c")
        assert storage.catalogs()[0].pages == []
