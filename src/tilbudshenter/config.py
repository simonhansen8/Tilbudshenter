"""Indlæsning af brugerens konfiguration (TOML)."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_NAME = "tilbudshenter.toml"


@dataclass
class Config:
    # Placering - bruges til at finde aviser fra butikker i nærheden
    latitude: float = 55.6761
    longitude: float = 12.5683
    radius_km: float = 15.0

    # Hvilke butikker/aviser der er relevante. Tom liste = alle.
    stores: list[str] = field(default_factory=list)
    exclude_stores: list[str] = field(default_factory=list)

    # Hvilke aviser hos de valgte butikker. Matches på dele af avisens navn,
    # fx "uge" eller "legetøj". Tom liste = alle.
    catalogs: list[str] = field(default_factory=list)
    exclude_catalogs: list[str] = field(default_factory=list)

    # Hvilke typer tilbud der er relevante. Tom liste = alle.
    categories: list[str] = field(default_factory=list)
    exclude_categories: list[str] = field(default_factory=list)
    custom_categories: dict[str, dict] = field(default_factory=dict)

    # Finere filtre
    min_discount_pct: float = 0.0
    only_known_discount: bool = False
    max_price: float | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    favorites: list[str] = field(default_factory=list)
    favorite_bonus: float = 15.0

    # Rapport
    top_n: int = 0  # 0 = alle
    per_category: int = 0  # 0 = ingen grænse pr. kategori
    output_dir: Path = Path("rapporter")
    formats: list[str] = field(default_factory=lambda: ["html", "md", "json"])

    # Data
    database: Path = Path("tilbud.db")
    api_key: str | None = None

    source_path: Path | None = None


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_config(path: Path | None = None) -> Config:
    """Indlæser konfiguration. Mangler filen, bruges standardværdier."""
    if path is None:
        path = Path(DEFAULT_CONFIG_NAME)
    if not path.exists():
        cfg = Config()
        base = Path.cwd()
    else:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        cfg = _from_dict(data)
        cfg.source_path = path
        base = path.resolve().parent
    cfg.output_dir = _resolve(base, cfg.output_dir)
    cfg.database = _resolve(base, cfg.database)
    return cfg


def _from_dict(data: dict) -> Config:
    cfg = Config()
    loc = data.get("placering", {})
    cfg.latitude = float(loc.get("breddegrad", cfg.latitude))
    cfg.longitude = float(loc.get("laengdegrad", cfg.longitude))
    cfg.radius_km = float(loc.get("radius_km", cfg.radius_km))

    stores = data.get("butikker", {})
    cfg.stores = list(stores.get("vaelg", []))
    cfg.exclude_stores = list(stores.get("fravaelg", []))

    catalogs = data.get("aviser", {})
    cfg.catalogs = list(catalogs.get("vaelg", []))
    cfg.exclude_catalogs = list(catalogs.get("fravaelg", []))

    cats = data.get("kategorier", {})
    cfg.categories = list(cats.get("vaelg", []))
    cfg.exclude_categories = list(cats.get("fravaelg", []))
    cfg.custom_categories = dict(cats.get("egne", {}))

    flt = data.get("filtre", {})
    cfg.min_discount_pct = float(flt.get("min_rabat_procent", cfg.min_discount_pct))
    cfg.only_known_discount = bool(flt.get("kun_kendt_rabat", cfg.only_known_discount))
    if flt.get("max_pris") is not None:
        cfg.max_price = float(flt["max_pris"])
    cfg.include_keywords = list(flt.get("skal_indeholde", []))
    cfg.exclude_keywords = list(flt.get("udelad_ord", []))
    cfg.favorites = list(flt.get("favoritter", []))
    cfg.favorite_bonus = float(flt.get("favorit_bonus", cfg.favorite_bonus))

    rep = data.get("rapport", {})
    cfg.top_n = int(rep.get("antal", cfg.top_n))
    cfg.per_category = int(rep.get("pr_kategori", cfg.per_category))
    cfg.output_dir = Path(rep.get("mappe", cfg.output_dir))
    cfg.formats = list(rep.get("formater", cfg.formats))

    store = data.get("data", {})
    cfg.database = Path(store.get("database", cfg.database))
    cfg.api_key = store.get("api_noegle") or None
    return cfg


def _toml(value) -> str:
    """Formaterer en simpel værdi som TOML (JSON-strenge er gyldige i TOML)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value)) if isinstance(value, float) else str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def _relative(path: Path, base: Path | None) -> str:
    if base is not None:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def render_config(cfg: Config, base: Path | None = None) -> str:
    """Skriver konfigurationen som TOML med forklarende kommentarer."""
    t = _toml
    custom = "".join(
        f"\n[kategorier.egne.{key}]\nnavn = {t(spec.get('navn', key))}\n"
        f"noegleord = {t(spec.get('noegleord', []))}\n"
        for key, spec in cfg.custom_categories.items()
    )
    if not custom:
        custom = """
# Egne kategorier eller ekstra nøgleord til eksisterende kategorier:
# [kategorier.egne.morgenmad]
# navn = "Morgenmad"
# noegleord = ["havregryn", "müsli", "skyr"]
"""
    max_price = f"max_pris = {t(cfg.max_price)}" if cfg.max_price is not None else "# max_pris = 100"
    api_key = f"api_noegle = {t(cfg.api_key)}" if cfg.api_key else '# api_noegle = ""'
    return f"""\
# Tilbudshenter - konfiguration
# Kan også ændres under "Indstillinger" i appen.
# Alle lister kan være tomme: tom liste betyder "alle".

[placering]
# Bruges til at finde de aviser, der gælder i dit område.
# Find koordinater fx ved at højreklikke på et sted i Google Maps.
breddegrad = {t(cfg.latitude)}
laengdegrad = {t(cfg.longitude)}
radius_km = {t(cfg.radius_km)}

[butikker]
# Hvilke butikker er relevante? Se mulighederne med: tilbudshenter butikker
vaelg = {t(cfg.stores)}
fravaelg = {t(cfg.exclude_stores)}

[aviser]
# Hvilke af butikkernes aviser er relevante? Matches på en del af avisens
# navn (store/små bogstaver er ligegyldige). Se navnene med: tilbudshenter butikker
vaelg = {t(cfg.catalogs)}
fravaelg = {t(cfg.exclude_catalogs)}

[kategorier]
# Hvilke typer tilbud er relevante? Se mulighederne med: tilbudshenter kategorier
# "andet" er tilbud, programmet ikke kunne placere i en kategori.
vaelg = {t(cfg.categories)}
fravaelg = {t(cfg.exclude_categories)}
{custom}
[filtre]
# Mange tilbud har ingen kendt førpris, så rabatten ikke kan beregnes.
# De vises sidst i listen, medmindre kun_kendt_rabat = true.
# min_rabat_procent skjuler tilbud, hvis kendte rabat er lavere.
min_rabat_procent = {t(cfg.min_discount_pct)}
kun_kendt_rabat = {t(cfg.only_known_discount)}
{max_price}
# skal_indeholde: hvis udfyldt, vises kun tilbud der nævner et af ordene.
# udelad_ord: tilbud der nævner et af ordene, skjules.
# favoritter: rykkes op på listen, fx ["kyllingebryst", "skyr"].
skal_indeholde = {t(cfg.include_keywords)}
udelad_ord = {t(cfg.exclude_keywords)}
favoritter = {t(cfg.favorites)}
favorit_bonus = {t(cfg.favorite_bonus)}

[rapport]
# antal: maks. antal tilbud i rapporterne (0 = alle).
# pr_kategori: maks. antal pr. kategori (0 = ingen grænse).
antal = {t(cfg.top_n)}
pr_kategori = {t(cfg.per_category)}
mappe = {t(_relative(cfg.output_dir, base))}
formater = {t(cfg.formats)}

[data]
database = {t(_relative(cfg.database, base))}
{api_key}
"""


def save_config(cfg: Config, path: Path) -> None:
    path.write_text(render_config(cfg, path.resolve().parent), encoding="utf-8")


def example_config() -> Config:
    return Config(
        stores=["Netto", "REMA 1000", "Lidl", "føtex", "Bilka", "365discount"],
        exclude_catalogs=["legetøj", "nonfood", "prosonic", "halloween", "ud af huset", "julekatalog"],
        categories=["koed", "fisk", "mejeri", "frugt_og_groent", "broed_og_bager", "kolonial", "frost", "kaffe_og_te"],
    )


EXAMPLE_CONFIG = render_config(example_config())
