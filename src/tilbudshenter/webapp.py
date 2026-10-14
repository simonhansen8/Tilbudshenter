"""Lokal web-app: knapper til at hente tilbud, filtre og indstillinger.

Startes med ``tilbudshenter app``. Serveren lytter kun på denne computer
(127.0.0.1) og åbner appen i browseren.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

from .categories import UNCATEGORIZED, Categorizer, merge_categories
from .cli import best_offers, load_app_config, make_source
from .config import Config, example_config, save_config
from .mealplan import ingredient_keys, plan_payload
from .opskrifter import extract_recipe, fetch
from .models import Offer
from .report import discount_text, kr, period_text, unit_price_text, write_reports
from .scanner import scan
from .selection import catalog_selected, store_selected
from .sources.base import SourceError
from .storage import Storage

DEFAULT_PORT = 8765

# Felter fra appens indstillinger -> Config-felter
_LIST_FIELDS = {
    "stores": "stores",
    "exclude_catalogs": "exclude_catalogs",
    "categories": "categories",
    "include_keywords": "include_keywords",
    "exclude_keywords": "exclude_keywords",
    "favorites": "favorites",
}
_FLOAT_FIELDS = {"latitude", "longitude", "radius_km", "min_discount_pct"}


class App:
    """Appens tilstand: konfiguration og en eventuel igangværende hentning."""

    def __init__(self, config_path: Path, demo: bool = False) -> None:
        self.config_path = config_path
        self.demo = demo
        self._lock = threading.Lock()
        self._scan = {"running": False, "done": 0, "total": 0, "message": "", "error": None, "result": None}
        if not config_path.exists():
            save_config(example_config(), config_path)

    def config(self) -> Config:
        return load_app_config(self.config_path, self.demo)

    def categorizer(self, cfg: Config) -> Categorizer:
        return Categorizer(merge_categories(cfg.custom_categories))

    # -- Status ---------------------------------------------------------
    def state(self) -> dict:
        cfg = self.config()
        categorizer = self.categorizer(cfg)
        now = datetime.now(timezone.utc)
        with Storage(cfg.database) as storage:
            catalogs = storage.catalogs(active_at=now)
            last = storage.last_scan()
        with self._lock:
            scan_state = dict(self._scan)
        return {
            "demo": self.demo,
            "scan": scan_state,
            "settings": settings_from_config(cfg),
            "catalog_count": len(catalogs),
            "last_scan": last.isoformat() if last else None,
            "categories": [
                {"key": key, "name": spec["navn"]} for key, spec in categorizer.categories.items()
            ] + [{"key": UNCATEGORIZED, "name": categorizer.display_name(UNCATEGORIZED)}],
        }

    def offers(self) -> dict:
        """Alle aktuelle tilbud fra de valgte butikker og aviser.

        Kategori- og rabatvalg anvendes i browseren, så de kan slås til og
        fra uden at hente igen.
        """
        cfg = self.config()
        categorizer = self.categorizer(cfg)
        wide = replace(
            cfg, categories=[], exclude_categories=[], min_discount_pct=0.0,
            only_known_discount=False, top_n=0, per_category=0,
        )
        with Storage(cfg.database) as storage:
            offers = best_offers(wide, storage, categorizer, datetime.now(timezone.utc), limit=0)
        return {"offers": [offer_payload(o, categorizer) for o in offers]}

    def catalogs(self) -> dict:
        """Butikker og aviser i området (kræver netværk)."""
        cfg = self.config()
        now = datetime.now(timezone.utc)
        catalogs = make_source(cfg, self.demo).list_catalogs(cfg.latitude, cfg.longitude, cfg.radius_km)
        stores: dict[str, list] = {}
        for c in catalogs:
            if c.run_till is None or c.run_till >= now:
                stores.setdefault(c.dealer, []).append(c)
        return {
            "stores": [
                {
                    "name": name,
                    "selected": store_selected(name, cfg),
                    "catalogs": [
                        {
                            "label": c.label.strip() or "(uden navn)",
                            "period": f"{c.run_from:%d/%m}-{c.run_till:%d/%m}" if c.run_from and c.run_till else "",
                            "selected": catalog_selected(c.label, cfg),
                        }
                        for c in sorted(items, key=lambda c: c.label.casefold())
                    ],
                }
                for name, items in sorted(stores.items(), key=lambda kv: kv[0].casefold())
            ]
        }

    # -- Indkøbsliste ---------------------------------------------------
    def shopping_list(self) -> dict:
        cfg = self.config()
        with Storage(cfg.database) as storage:
            items = storage.shopping_list()
        now = datetime.now(timezone.utc)
        for item in items:
            offer = Offer(
                id=item["id"], catalog_id="", dealer=item["dealer"] or "", heading=item["heading"],
                description=item["description"] or "", price=item["price"] or 0.0,
                amount=item["amount"], unit=item["unit"],
                run_from=datetime.fromisoformat(item["run_from"]) if item["run_from"] else None,
                run_till=datetime.fromisoformat(item["run_till"]) if item["run_till"] else None,
            )
            item.update(
                price_text=kr(item["price"]) if item["price"] is not None else "",
                unit_price_text=unit_price_text(offer) if item["price"] is not None else "",
                period_text=period_text(offer),
                expired=bool(offer.run_till and offer.run_till < now),
                member=offer.member,
            )
        return {"items": items}

    def change_list(self, data: dict) -> None:
        action = data.get("action")
        cfg = self.config()
        with Storage(cfg.database) as storage:
            note = str(data.get("note") or "")[:200] or None
            if action == "add":
                if not storage.add_to_list(str(data.get("id", "")), note):
                    raise ValueError("Tilbuddet findes ikke længere")
            elif action == "add_text":
                text = str(data.get("text", "")).strip()
                if not text:
                    raise ValueError("Skriv hvad der skal på listen")
                storage.add_text_to_list(text[:200], note, str(data.get("category") or "")[:40] or None)
            elif action == "check":
                storage.set_list_checked(str(data.get("id", "")), bool(data.get("checked")))
            elif action == "remove":
                storage.remove_from_list(str(data.get("id", "")))
            elif action == "clear":
                storage.clear_list(only_checked=bool(data.get("only_checked")))
            else:
                raise ValueError(f"Ukendt handling: {action}")

    # -- Handlinger -----------------------------------------------------
    def save_settings(self, data: dict) -> None:
        cfg = load_app_config(self.config_path, demo=False)
        cfg = apply_settings(cfg, data)
        save_config(cfg, self.config_path)

    def start_scan(self, force: bool) -> bool:
        with self._lock:
            if self._scan["running"]:
                return False
            self._scan = {"running": True, "done": 0, "total": 0, "message": "Finder aviser…", "error": None, "result": None}
        threading.Thread(target=self._run_scan, args=(force,), daemon=True).start()
        return True

    def _run_scan(self, force: bool) -> None:
        def progress(number: int, total: int, catalog) -> None:
            with self._lock:
                self._scan.update(done=number - 1, total=total, message=f"{catalog.dealer}: {catalog.label.strip()}")

        try:
            cfg = self.config()
            categorizer = self.categorizer(cfg)
            now = datetime.now(timezone.utc)
            with Storage(cfg.database) as storage:
                result = scan(cfg, make_source(cfg, self.demo), storage, categorizer,
                              force=force, now=now, progress=progress)
                offers = best_offers(cfg, storage, categorizer, now)
            write_reports(offers, categorizer, cfg.output_dir, cfg.formats, now)
            summary = {
                "new_catalogs": len(result.new_catalogs),
                "known_catalogs": len(result.known_catalogs),
                "offers_fetched": result.offers_fetched,
                "failed": [f"{c.dealer}: {c.label}" for c, _ in result.failed],
            }
            with self._lock:
                self._scan.update(running=False, done=self._scan["total"], message="", result=summary)
        except (SourceError, OSError) as exc:
            with self._lock:
                self._scan.update(running=False, message="", error=str(exc))
        except Exception as exc:  # Vis uventede fejl i appen i stedet for at gå i stå
            with self._lock:
                self._scan.update(running=False, message="", error=f"Uventet fejl: {exc!r}")


def offer_payload(o: Offer, categorizer: Categorizer) -> dict:
    """Et tilbud som appen viser det, med færdigformaterede tekster."""
    ingredients = ingredient_keys(o.heading)
    return {
        **o.to_dict(),
        # Ingredienser til madplanen; udeladt for de fleste tilbud
        **({"ingredients": ingredients} if ingredients else {}),
        "category_name": categorizer.display_name(o.category),
        "price_text": kr(o.price),
        "pre_price_text": kr(o.pre_price) if o.pre_price else "",
        "unit_price_text": unit_price_text(o),
        "discount_text": discount_text(o),
        "period_text": period_text(o),
    }


def settings_from_config(cfg: Config) -> dict:
    return {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "radius_km": cfg.radius_km,
        "stores": cfg.stores,
        "exclude_catalogs": cfg.exclude_catalogs,
        "categories": cfg.categories,
        "min_discount_pct": cfg.min_discount_pct,
        "only_known_discount": cfg.only_known_discount,
        "max_price": cfg.max_price,
        "include_keywords": cfg.include_keywords,
        "exclude_keywords": cfg.exclude_keywords,
        "favorites": cfg.favorites,
    }


def apply_settings(cfg: Config, data: dict) -> Config:
    """Opdaterer konfigurationen med værdier fra appen. Ukendte felter ignoreres."""
    changes: dict = {}
    for key, field_name in _LIST_FIELDS.items():
        if key in data:
            values = data[key]
            if not isinstance(values, list):
                raise ValueError(f"{key} skal være en liste")
            changes[field_name] = [str(v).strip() for v in values if str(v).strip()]
    for key in _FLOAT_FIELDS:
        if key in data:
            changes[key] = float(data[key])
    if "only_known_discount" in data:
        changes["only_known_discount"] = bool(data["only_known_discount"])
    if "max_price" in data:
        value = data["max_price"]
        changes["max_price"] = float(value) if value not in (None, "") else None
    if "radius_km" in changes and changes["radius_km"] <= 0:
        raise ValueError("Radius skal være større end 0")
    return replace(cfg, **changes)


class Handler(BaseHTTPRequestHandler):
    app: App
    port: int

    def log_message(self, format: str, *args) -> None:  # Hold konsollen ren
        pass

    # Beskyttelse mod at andre hjemmesider styrer appen: kun forespørgsler til
    # localhost, og ændringer kræver en header, som browsere ikke sender
    # på tværs af sider uden tilladelse.
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "Ukendt vært")
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                html = resources.files("tilbudshenter.data").joinpath("app.html").read_bytes()
                return self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(self.app.state())
            if path == "/api/offers":
                return self._json(self.app.offers())
            if path == "/api/catalogs":
                return self._json(self.app.catalogs())
            if path == "/api/list":
                return self._json(self.app.shopping_list())
            if path == "/api/recipes":
                return self._json(plan_payload())
        except SourceError as exc:
            return self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        except Exception as exc:
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Fejl: {exc}")
        self._error(HTTPStatus.NOT_FOUND, "Ikke fundet")

    def do_POST(self) -> None:
        if not self._host_ok() or self.headers.get("X-Tilbudshenter") != "1":
            return self._error(HTTPStatus.FORBIDDEN, "Afvist")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except (ValueError, json.JSONDecodeError):
            return self._error(HTTPStatus.BAD_REQUEST, "Ugyldige data")
        path = urlparse(self.path).path
        try:
            if path == "/api/scan":
                if not self.app.start_scan(force=bool(data.get("force"))):
                    return self._error(HTTPStatus.CONFLICT, "Der hentes allerede tilbud")
                return self._json({"ok": True})
            if path == "/api/settings":
                self.app.save_settings(data)
                return self._json({"ok": True})
            if path == "/api/list":
                self.app.change_list(data)
                return self._json(self.app.shopping_list())
            if path == "/api/import_recipe":
                return self._json({"recipe": import_recipe(str(data.get("url", "")))})
        except (ValueError, TypeError) as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Fejl: {exc}")
        self._error(HTTPStatus.NOT_FOUND, "Ikke fundet")


def import_recipe(url: str) -> dict:
    """Opskriften på en madside, til brugerens egne opskrifter."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Skriv hele adressen på opskriften, fx https://...")
    try:
        page = fetch(url)
    except OSError as exc:
        raise ValueError(f"Kunne ikke hente siden: {exc}") from exc
    recipe = extract_recipe(page, url)
    if not recipe:
        raise ValueError("Fandt ingen opskrift på siden. Kopiér i stedet ingredienslisten ind.")
    return recipe


def make_server(app: App, port: int = DEFAULT_PORT, tries: int = 10) -> ThreadingHTTPServer:
    """Starter på den første ledige port fra ``port``."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    last_error: OSError | None = None
    for candidate in range(port, port + tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last_error = exc
    raise OSError(f"Ingen ledig port mellem {port} og {port + tries - 1}") from last_error


def run(config_path: Path, demo: bool = False, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    app = App(config_path, demo=demo)
    server = make_server(app, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Tilbudshenter kører på {url}")
    print("Luk dette vindue (eller tryk Ctrl+C) for at stoppe programmet.")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
