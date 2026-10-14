"""Statisk udgave af appen til GitHub Pages.

En GitHub Actions-workflow henter aviserne (det kan browseren ikke selv,
da Tjek ikke tillader kald fra andre hjemmesider) og bygger en mappe med
``index.html`` og ``data.json``. Siden læser tilbuddene fra ``data.json``,
og brugerens indstillinger og indkøbsliste gemmes i browseren.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .categories import UNCATEGORIZED, Categorizer, merge_categories
from .cli import best_offers
from .config import NEW_STORES, Config, example_config
from .storage import Storage
from .webapp import offer_payload, settings_from_config

# Butikker der hentes til siden. Brugeren vælger blandt dem i browseren;
# standardvalget er det samme som i en ny konfiguration.
SITE_STORES = [
    "Netto", "REMA 1000", "Lidl", "føtex", "Bilka", "365discount", *NEW_STORES,
    "Coop", "Min Købmand", "LET-KØB",
]

STATIC_MARKER = "<script>window.TILBUDSHENTER_STATIC = true;</script>"


def site_config() -> Config:
    """Konfigurationen workflowen henter med: alle butikker siden tilbyder,
    og ingen af brugerens filtre (de anvendes i browseren)."""
    base = example_config()
    return replace(base, stores=list(SITE_STORES), categories=[])


def site_data(cfg: Config, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    categorizer = Categorizer(merge_categories(cfg.custom_categories))
    wide = replace(
        cfg, categories=[], exclude_categories=[], min_discount_pct=0.0, only_known_discount=False,
        max_price=None, include_keywords=[], exclude_keywords=[], favorites=[], top_n=0, per_category=0,
    )
    with Storage(cfg.database) as storage:
        offers = best_offers(wide, storage, categorizer, now, limit=0)
        catalogs = storage.catalogs(active_at=now)
        last = storage.last_scan()

    stores: dict[str, list] = {}
    for c in catalogs:
        stores.setdefault(c.dealer, []).append(c)
    defaults = settings_from_config(example_config())
    defaults.update(latitude=cfg.latitude, longitude=cfg.longitude, radius_km=cfg.radius_km)
    return {
        "generated": now.isoformat(),
        "last_scan": last.isoformat() if last else None,
        "catalog_count": len(catalogs),
        "favorite_bonus": cfg.favorite_bonus,
        "default_settings": defaults,
        "categories": [
            {"key": key, "name": spec["navn"]} for key, spec in categorizer.categories.items()
        ] + [{"key": UNCATEGORIZED, "name": categorizer.display_name(UNCATEGORIZED)}],
        "stores": [
            {
                "name": name,
                "catalogs": [
                    {
                        "label": c.label.strip() or "(uden navn)",
                        "period": f"{c.run_from:%d/%m}-{c.run_till:%d/%m}" if c.run_from and c.run_till else "",
                    }
                    for c in sorted(items, key=lambda c: c.label.casefold())
                ],
            }
            for name, items in sorted(stores.items(), key=lambda kv: kv[0].casefold())
        ],
        "offers": [offer_payload(o, categorizer) for o in offers],
    }


def static_html() -> str:
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    return html.replace("<script>\n", STATIC_MARKER + "\n<script>\n", 1)


def build_site(cfg: Config, out_dir: Path, now: datetime | None = None) -> dict:
    """Skriver index.html og data.json i ``out_dir``. Returnerer dataene."""
    data = site_data(cfg, now)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(static_html(), encoding="utf-8")
    (out_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return data
