"""Kommandolinje: tilbudshenter <kommando>."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .categories import Categorizer, merge_categories
from .config import DEFAULT_CONFIG_NAME, EXAMPLE_CONFIG, Config, load_config
from .report import render_html, render_json, render_markdown, render_text, write_reports
from .scanner import scan
from .selection import catalog_selected, select_offers, store_selected
from .sources.base import OfferSource, SourceError
from .storage import Storage


def make_source(cfg: Config, demo: bool) -> OfferSource:
    if demo:
        from .sources.demo import DemoSource

        return DemoSource()
    from .sources.tjek import TjekSource

    return TjekSource(api_key=cfg.api_key)


def load_app_config(path: Path | None, demo: bool) -> Config:
    cfg = load_config(path)
    if demo:
        # Demodata holdes adskilt fra de rigtige data
        cfg.database = cfg.database.with_suffix(".demo.db")
        cfg.output_dir = cfg.output_dir / "demo"
    return cfg


def prepare_config(args: argparse.Namespace) -> Config:
    return load_app_config(args.config, args.demo)


def best_offers(cfg: Config, storage: Storage, categorizer: Categorizer, now: datetime, limit: int | None = None):
    current = storage.current_offers(now)
    current_catalogs = {o.catalog_id for o in current}
    typical = storage.typical_unit_prices(exclude_catalogs=current_catalogs)
    return select_offers(current, cfg, categorizer, typical, limit=limit)


# -- Kommandoer ---------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    path = args.config or Path(DEFAULT_CONFIG_NAME)
    if path.exists() and not args.force:
        print(f"{path} findes allerede (brug --force for at overskrive).")
        return 1
    path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    print(f"Oprettede {path}. Ret butikker, kategorier og placering til, og kør: tilbudshenter scan")
    return 0


def run_scan(args: argparse.Namespace, cfg: Config) -> int:
    categorizer = Categorizer(merge_categories(cfg.custom_categories))
    now = datetime.now(timezone.utc)
    with Storage(cfg.database) as storage:
        try:
            result = scan(cfg, make_source(cfg, args.demo), storage, categorizer, force=args.force, now=now)
        except SourceError as exc:
            print(f"Fejl: {exc}", file=sys.stderr)
            return 2

        for catalog, error in result.failed:
            print(f"Advarsel: kunne ikke hente {catalog.dealer} ({catalog.label}): {error}", file=sys.stderr)
        if result.found_new:
            names = ", ".join(sorted({c.dealer for c in result.new_catalogs}))
            print(f"{len(result.new_catalogs)} nye aviser ({names}) - {result.offers_fetched} tilbud hentet.")
        else:
            print(f"Ingen nye aviser ({len(result.known_catalogs)} kendte er stadig aktive).")
            if not args.always_report:
                return 0

        offers = best_offers(cfg, storage, categorizer, now)
    title = "Ugens bedste tilbud" + (" (demo)" if args.demo else "")
    paths = write_reports(offers, categorizer, cfg.output_dir, cfg.formats, now, title=title)
    known = sum(1 for o in offers if o.known_discount is not None)
    print(f"\n{len(offers)} tilbud matcher dine valg ({known} med kendt rabat). De bedste:\n")
    print(render_text(offers[: args.show], categorizer))
    if paths:
        print(f"\nRapporter gemt i {cfg.output_dir} (fx {paths[0].name})")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    return run_scan(args, prepare_config(args))


def cmd_watch(args: argparse.Namespace) -> int:
    cfg = prepare_config(args)
    print(f"Overvåger tilbudsaviser hver {args.interval:g}. time. Stop med Ctrl+C.")
    try:
        while True:
            print(f"\n[{datetime.now():%d/%m %H:%M}] Scanner...")
            run_scan(args, cfg)
            time.sleep(args.interval * 3600)
    except KeyboardInterrupt:
        return 0


def cmd_offers(args: argparse.Namespace) -> int:
    cfg = prepare_config(args)
    # Kommandolinjens valg tilsidesætter konfigurationen for denne visning
    overrides = {}
    if args.all:
        overrides.update(stores=[], categories=[], exclude_categories=[], min_discount_pct=0.0)
    if args.store:
        overrides["stores"] = args.store
    if args.category:
        overrides["categories"] = args.category
    if args.min_discount is not None:
        overrides["min_discount_pct"] = args.min_discount
    if args.search:
        overrides["include_keywords"] = args.search
    if args.per_category is not None:
        overrides["per_category"] = args.per_category
    cfg = replace(cfg, **overrides)

    categorizer = Categorizer(merge_categories(cfg.custom_categories))
    now = datetime.now(timezone.utc)
    with Storage(cfg.database) as storage:
        if not storage.catalogs(active_at=now):
            print("Ingen aktive aviser i databasen endnu. Kør først: tilbudshenter scan")
            return 1
        offers = best_offers(cfg, storage, categorizer, now, limit=args.count)

    title = "Bedste tilbud"
    renderers = {
        "tekst": lambda: render_text(offers, categorizer),
        "md": lambda: render_markdown(offers, categorizer, title, now),
        "html": lambda: render_html(offers, categorizer, title, now),
        "json": lambda: render_json(offers, categorizer, now),
    }
    content = renderers[args.format]()
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"Gemt i {args.output}")
    else:
        print(content)
    return 0


def cmd_stores(args: argparse.Namespace) -> int:
    cfg = prepare_config(args)
    try:
        catalogs = make_source(cfg, args.demo).list_catalogs(cfg.latitude, cfg.longitude, cfg.radius_km)
    except SourceError as exc:
        print(f"Fejl: {exc}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    by_store: dict[str, list] = {}
    for c in catalogs:
        if c.run_till is None or c.run_till >= now:
            by_store.setdefault(c.dealer, []).append(c)
    print(f"Butikker og aviser inden for {cfg.radius_km:g} km ([x] = valgt i din konfiguration):")
    for name in sorted(by_store, key=str.casefold):
        store_on = store_selected(name, cfg)
        print(f"\n  [{'x' if store_on else ' '}] {name}")
        for c in sorted(by_store[name], key=lambda c: c.label.casefold()):
            mark = "x" if store_on and catalog_selected(c.label, cfg) else " "
            period = f" ({c.run_from:%d/%m}-{c.run_till:%d/%m})" if c.run_from and c.run_till else ""
            print(f"        [{mark}] {c.label.strip() or '(uden navn)'}{period}")
    return 0


def cmd_categories(args: argparse.Namespace) -> int:
    cfg = prepare_config(args)
    categories = merge_categories(cfg.custom_categories)
    print("Kategorier ([x] = valgt i din konfiguration). Brug nøglen i konfigurationen.\n")
    for key, spec in categories.items():
        selected = (not cfg.categories or key in cfg.categories) and key not in cfg.exclude_categories
        words = ", ".join(w.strip() for w in spec["noegleord"][:8])
        print(f"  [{'x' if selected else ' '}] {key:<16} {spec['navn']:<20} fx {words} …")
    print("  [ ] andet            Andet                Tilbud der ikke passer i en kategori")
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    from .webapp import run

    run(args.config or Path(DEFAULT_CONFIG_NAME), demo=args.demo, port=args.port, open_browser=not args.no_browser)
    return 0


# -- Parser -------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", type=Path, help=f"konfigurationsfil (standard: {DEFAULT_CONFIG_NAME})")
    common.add_argument("--demo", action="store_true", help="brug indbyggede demodata i stedet for internettet")
    common.add_argument("-v", "--verbose", action="store_true", help="vis flere detaljer")

    parser = argparse.ArgumentParser(
        prog="tilbudshenter",
        description="Scanner tilbudsaviser og finder de bedste tilbud.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("app", aliases=["ui"], parents=[common], help="åbn appen i browseren")
    p.add_argument("--port", type=int, default=8765, help="port (standard: 8765)")
    p.add_argument("--ingen-browser", dest="no_browser", action="store_true", help="åbn ikke browseren automatisk")
    p.set_defaults(func=cmd_app)

    p = sub.add_parser("init", parents=[common], help="opret en konfigurationsfil")
    p.add_argument("--force", action="store_true", help="overskriv eksisterende fil")
    p.set_defaults(func=cmd_init)

    def add_scan_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--force", action="store_true", help="hent også aviser der allerede er scannet")
        p.add_argument("--altid-rapport", dest="always_report", action="store_true",
                       help="lav rapport selv om der ikke er nye aviser")
        p.add_argument("--vis", dest="show", type=int, default=20, help="antal tilbud vist i terminalen")

    p = sub.add_parser("scan", parents=[common], help="find nye aviser og lav rapport over de bedste tilbud")
    add_scan_args(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("overvaag", aliases=["watch"], parents=[common], help="scan automatisk med fast interval")
    add_scan_args(p)
    p.add_argument("--interval", type=float, default=6, help="timer mellem scanninger (standard: 6)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("tilbud", parents=[common], help="vis de bedste aktuelle tilbud")
    p.add_argument("-b", "--butik", dest="store", action="append", help="kun denne butik (kan gentages)")
    p.add_argument("-k", "--kategori", dest="category", action="append", help="kun denne kategori (kan gentages)")
    p.add_argument("-s", "--soeg", dest="search", action="append", help="kun tilbud der nævner ordet (kan gentages)")
    p.add_argument("--min-rabat", dest="min_discount", type=float, help="mindste rabat i procent")
    p.add_argument("--pr-kategori", dest="per_category", type=int, help="maks. antal pr. kategori")
    p.add_argument("-n", "--antal", dest="count", type=int, help="antal tilbud")
    p.add_argument("--alle", dest="all", action="store_true", help="ignorér konfigurationens butiks-, kategori- og rabatvalg")
    p.add_argument("-f", "--format", choices=["tekst", "md", "html", "json"], default="tekst")
    p.add_argument("-o", "--output", type=Path, help="gem i fil i stedet for at vise")
    p.set_defaults(func=cmd_offers)

    p = sub.add_parser("butikker", parents=[common], help="vis butikker med aviser i dit område")
    p.set_defaults(func=cmd_stores)

    p = sub.add_parser("kategorier", parents=[common], help="vis tilgængelige kategorier")
    p.set_defaults(func=cmd_categories)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
