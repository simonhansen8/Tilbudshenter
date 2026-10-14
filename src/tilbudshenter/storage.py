"""SQLite-lager for aviser, tilbud og prishistorik.

Databasen husker hvilke aviser der allerede er scannet (så kun nye aviser
hentes), og gemmer alle tilbud. Det giver en prishistorik, som bruges til
at vurdere tilbud uden førpris - og som en kommende madplan kan bygge på.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .models import Catalog, Offer

# Hæves, når der hentes mere om hver avis end før, så allerede scannede
# aviser hentes igen én gang. 2: sidetal, rækkefølge og sidebilleder.
SCAN_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS catalogs (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    dealer      TEXT NOT NULL,
    label       TEXT,
    run_from    TEXT,
    run_till    TEXT,
    offer_count INTEGER,
    first_seen  TEXT NOT NULL,
    scanned_at  TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id          TEXT PRIMARY KEY,
    catalog_id  TEXT NOT NULL REFERENCES catalogs(id),
    dealer      TEXT NOT NULL,
    heading     TEXT NOT NULL,
    description TEXT,
    product_key TEXT NOT NULL,
    price       REAL NOT NULL,
    pre_price   REAL,
    currency    TEXT,
    amount      REAL,
    unit        TEXT,
    unit_price  REAL,
    category    TEXT,
    run_from    TEXT,
    run_till    TEXT,
    image_url   TEXT,
    fetched_at  TEXT NOT NULL
);

-- Indkøbslisten gemmer en kopi af tilbuddet, så den overlever, at
-- tilbuddet udløber. Egne varer har ingen pris.
CREATE TABLE IF NOT EXISTS shopping_list (
    id          TEXT PRIMARY KEY,
    dealer      TEXT,
    heading     TEXT NOT NULL,
    description TEXT,
    price       REAL,
    unit        TEXT,
    amount      REAL,
    run_from    TEXT,
    run_till    TEXT,
    added_at    TEXT NOT NULL,
    checked     INTEGER NOT NULL DEFAULT 0,
    note        TEXT,  -- fx hvilke retter i madplanen varen skal bruges til
    category    TEXT   -- afdelingen i butikken
);

CREATE INDEX IF NOT EXISTS offers_run_till ON offers(run_till);
CREATE INDEX IF NOT EXISTS offers_product ON offers(product_key, unit);
"""


def product_key(heading: str) -> str:
    """Normaliseret varenavn til sammenligning over tid."""
    return re.sub(r"[^\w]+", " ", heading.casefold()).strip()


def _iso(value: datetime | None) -> str | None:
    """Gemmes altid i UTC, så datoer kan sammenlignes som tekst i SQL."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # Kolonner der er kommet til siden databasen blev oprettet
        added = {
            "shopping_list": {"note": "TEXT", "category": "TEXT"},
            "catalogs": {"url": "TEXT", "pages": "TEXT", "scan_version": "INTEGER"},
            "offers": {"catalog_page": "INTEGER", "catalog_order": "INTEGER"},
        }
        for table, wanted in added.items():
            columns = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for column, kind in wanted.items():
                if column not in columns:
                    try:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
                    except sqlite3.OperationalError as exc:
                        # En anden forbindelse (fx hentningen i appen) nåede det først
                        if "duplicate column" not in str(exc):
                            raise

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- Aviser ---------------------------------------------------------
    def is_scanned(self, catalog_id: str) -> bool:
        row = self.conn.execute(
            "SELECT scanned_at, scan_version FROM catalogs WHERE id = ?", (catalog_id,)
        ).fetchone()
        return bool(row and row["scanned_at"] and (row["scan_version"] or 0) >= SCAN_VERSION)

    def save_catalog(self, catalog: Catalog, source: str, scanned: bool) -> None:
        self.conn.execute(
            """
            INSERT INTO catalogs (id, source, dealer, label, run_from, run_till,
                                  offer_count, first_seen, scanned_at, url, pages, scan_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                dealer = excluded.dealer, label = excluded.label,
                run_from = excluded.run_from, run_till = excluded.run_till,
                offer_count = excluded.offer_count,
                scanned_at = COALESCE(excluded.scanned_at, catalogs.scanned_at),
                url = COALESCE(excluded.url, catalogs.url),
                pages = COALESCE(excluded.pages, catalogs.pages),
                scan_version = COALESCE(excluded.scan_version, catalogs.scan_version)
            """,
            (
                catalog.id, source, catalog.dealer, catalog.label,
                _iso(catalog.run_from), _iso(catalog.run_till), catalog.offer_count,
                _now(), _now() if scanned else None, catalog.url,
                json.dumps(catalog.pages) if catalog.pages else None, SCAN_VERSION if scanned else None,
            ),
        )
        self.conn.commit()

    def catalogs(self, active_at: datetime | None = None) -> list[Catalog]:
        sql = "SELECT * FROM catalogs WHERE scanned_at IS NOT NULL"
        params: tuple = ()
        if active_at is not None:
            sql += " AND (run_till IS NULL OR run_till >= ?)"
            params = (_iso(active_at),)
        rows = self.conn.execute(sql + " ORDER BY dealer, run_from", params).fetchall()
        return [
            Catalog(
                id=r["id"], dealer=r["dealer"], label=r["label"],
                run_from=_dt(r["run_from"]), run_till=_dt(r["run_till"]),
                offer_count=r["offer_count"], url=r["url"],
                pages=json.loads(r["pages"]) if r["pages"] else [],
            )
            for r in rows
        ]

    def last_scan(self) -> datetime | None:
        row = self.conn.execute("SELECT MAX(scanned_at) AS last FROM catalogs").fetchone()
        return _dt(row["last"]) if row and row["last"] else None

    # -- Tilbud ---------------------------------------------------------
    def save_offers(self, offers: list[Offer]) -> None:
        now = _now()
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO offers (
                id, catalog_id, dealer, heading, description, product_key, price,
                pre_price, currency, amount, unit, unit_price, category,
                run_from, run_till, image_url, fetched_at, catalog_page, catalog_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    o.id, o.catalog_id, o.dealer, o.heading, o.description,
                    product_key(o.heading), o.price, o.pre_price, o.currency,
                    o.amount, o.unit, o.unit_price, o.category,
                    _iso(o.run_from), _iso(o.run_till), o.image_url, now,
                    o.catalog_page, o.catalog_order,
                )
                for o in offers
            ],
        )
        self.conn.commit()

    def current_offers(self, at: datetime | None = None) -> list[Offer]:
        """Tilbud der gælder nu eller senere (ikke udløbne)."""
        at = at or datetime.now(timezone.utc)
        rows = self.conn.execute(
            """
            SELECT o.*, c.label AS catalog_label
            FROM offers o LEFT JOIN catalogs c ON c.id = o.catalog_id
            WHERE o.run_till IS NULL OR o.run_till >= ?
            """,
            (_iso(at),),
        ).fetchall()
        offers = [
            Offer(
                id=r["id"], catalog_id=r["catalog_id"], dealer=r["dealer"],
                heading=r["heading"], description=r["description"] or "",
                price=r["price"], pre_price=r["pre_price"],
                currency=r["currency"] or "DKK", amount=r["amount"], unit=r["unit"],
                run_from=_dt(r["run_from"]), run_till=_dt(r["run_till"]),
                image_url=r["image_url"], category=r["category"],
                catalog_label=r["catalog_label"] or "",
                catalog_page=r["catalog_page"], catalog_order=r["catalog_order"],
            )
            for r in rows
        ]
        # Fortolkningen af beskrivelser kan være forbedret, siden tilbuddet blev hentet
        for offer in offers:
            offer.enrich_from_text()
        return offers

    def price_lows(self, offers: list[Offer], min_weeks: int = 3) -> dict[str, int]:
        """Finder tilbud med den laveste pris i mindst ``min_weeks`` uger.

        Et tilbud tæller, når prisen pr. kg/liter/stk er lavere end alle
        tidligere tilbud på samme vare (samme navn) i alle butikker, og
        historikken går mindst ``min_weeks`` uger tilbage. Returnerer
        {tilbuds-id: antal uger}.
        """
        rows = self.conn.execute(
            "SELECT product_key, unit, unit_price, run_from, catalog_id FROM offers "
            "WHERE unit_price IS NOT NULL AND run_from IS NOT NULL"
        ).fetchall()
        history: dict[tuple[str, str], list[tuple[datetime, float, str]]] = {}
        for r in rows:
            history.setdefault((r["product_key"], r["unit"]), []).append(
                (_dt(r["run_from"]), r["unit_price"], r["catalog_id"])
            )
        result: dict[str, int] = {}
        for offer in offers:
            if not offer.unit_price or not offer.unit or offer.run_from is None:
                continue
            start = _dt(_iso(offer.run_from))
            earlier = [
                (when, price)
                for when, price, catalog in history.get((product_key(offer.heading), offer.unit), [])
                if catalog != offer.catalog_id and when < start
            ]
            if not earlier:
                continue
            weeks = (start - min(when for when, _ in earlier)).days // 7
            if weeks >= min_weeks and offer.unit_price < min(price for _, price in earlier) - 0.005:
                result[offer.id] = weeks
        return result

    def typical_unit_prices(self, exclude_catalogs: set[str] | None = None) -> dict[tuple[str, str], float]:
        """Median-enhedspris pr. vare fra tidligere aviser.

        Bruges som "normalpris" for tilbud uden førpris. Kun varer set i
        mindst to tidligere aviser medtages.
        """
        exclude_catalogs = exclude_catalogs or set()
        rows = self.conn.execute(
            "SELECT product_key, unit, unit_price, catalog_id FROM offers WHERE unit_price IS NOT NULL"
        ).fetchall()
        prices: dict[tuple[str, str], list[float]] = {}
        catalogs_seen: dict[tuple[str, str], set[str]] = {}
        for r in rows:
            if r["catalog_id"] in exclude_catalogs:
                continue
            key = (r["product_key"], r["unit"])
            prices.setdefault(key, []).append(r["unit_price"])
            catalogs_seen.setdefault(key, set()).add(r["catalog_id"])
        return {
            key: statistics.median(values)
            for key, values in prices.items()
            if len(catalogs_seen[key]) >= 2
        }

    def prune(self, before: datetime) -> int:
        """Sletter aviser og tilbud, der udløb før ``before``, så databasen
        ikke vokser uden grænse. Returnerer antallet af slettede tilbud."""
        cutoff = _iso(before)
        deleted = self.conn.execute("DELETE FROM offers WHERE run_till < ?", (cutoff,)).rowcount
        self.conn.execute(
            "DELETE FROM catalogs WHERE run_till < ? AND id NOT IN (SELECT catalog_id FROM offers)", (cutoff,)
        )
        self.conn.commit()
        if deleted:
            self.conn.execute("VACUUM")
        return deleted

    # -- Indkøbsliste ---------------------------------------------------
    def shopping_list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM shopping_list ORDER BY dealer IS NULL, dealer, added_at"
        ).fetchall()
        return [{**dict(r), "checked": bool(r["checked"])} for r in rows]

    def add_to_list(self, offer_id: str, note: str | None = None) -> bool:
        """Lægger et tilbud på listen. Returnerer False, hvis tilbuddet ikke findes."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO shopping_list
                (id, dealer, heading, description, price, unit, amount, run_from, run_till, added_at, category)
            SELECT id, dealer, heading, description, price, unit, amount, run_from, run_till, ?, category
            FROM offers WHERE id = ?
            """,
            (_now(), offer_id),
        )
        if note:
            self.conn.execute("UPDATE shopping_list SET note = ? WHERE id = ?", (note, offer_id))
        self.conn.commit()
        return cur.rowcount > 0 or self.conn.execute(
            "SELECT 1 FROM shopping_list WHERE id = ?", (offer_id,)
        ).fetchone() is not None

    def add_text_to_list(self, text: str, note: str | None = None, category: str | None = None) -> str:
        """Lægger en egen vare (fx "mælk") på listen."""
        item_id = f"egen-{datetime.now(timezone.utc).timestamp():.6f}"
        self.conn.execute(
            "INSERT INTO shopping_list (id, heading, added_at, note, category) VALUES (?, ?, ?, ?, ?)",
            (item_id, text.strip(), _now(), note, category),
        )
        self.conn.commit()
        return item_id

    def set_list_checked(self, item_id: str, checked: bool) -> None:
        self.conn.execute("UPDATE shopping_list SET checked = ? WHERE id = ?", (int(checked), item_id))
        self.conn.commit()

    def remove_from_list(self, item_id: str) -> None:
        self.conn.execute("DELETE FROM shopping_list WHERE id = ?", (item_id,))
        self.conn.commit()

    def clear_list(self, only_checked: bool = False) -> None:
        self.conn.execute("DELETE FROM shopping_list" + (" WHERE checked = 1" if only_checked else ""))
        self.conn.commit()
