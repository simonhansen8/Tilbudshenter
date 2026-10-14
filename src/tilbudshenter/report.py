"""Rapporter over de bedste tilbud: terminal, Markdown, HTML og JSON."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .categories import Categorizer
from .models import Offer

UNIT_LABEL = {"kg": "kg", "l": "l", "stk": "stk"}


def kr(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.2f} kr".replace(",", "X").replace(".", ",").replace("X", ".")


def unit_price_text(offer: Offer) -> str:
    if offer.unit_price is None or offer.unit is None:
        return ""
    if offer.unit == "stk" and offer.amount == 1:
        return ""  # "pr. stk" for én vare siger intet nyt
    return f"{kr(offer.unit_price)}/{UNIT_LABEL.get(offer.unit, offer.unit)}"


def period_text(offer: Offer) -> str:
    def fmt(d: datetime | None) -> str:
        return d.astimezone().strftime("%d/%m") if d else "?"

    if not offer.run_from and not offer.run_till:
        return ""
    return f"{fmt(offer.run_from)}-{fmt(offer.run_till)}"


def discount_text(offer: Offer) -> str:
    """Rabat ift. normalprisen, eller "ca. -25%" når den er anslået ud fra
    prishistorik eller andre butikkers priser."""
    if offer.discount_pct:
        return f"-{offer.discount_pct:.0f}%"
    if offer.known_discount:
        return f"ca. -{offer.known_discount:.0f}%"
    return ""


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


# -- Terminal -----------------------------------------------------------
def render_text(offers: list[Offer], categorizer: Categorizer) -> str:
    if not offers:
        return "Ingen tilbud matcher dine valg."
    rows = [("#", "Butik", "Vare", "Pris", "Rabat", "Enhedspris", "Kategori", "Gælder")]
    for i, o in enumerate(offers, 1):
        rows.append((
            str(i), _short(o.dealer, 14), _short(o.heading, 34), kr(o.price),
            discount_text(o), unit_price_text(o),
            _short(categorizer.display_name(o.category), 16), period_text(o),
        ))
    widths = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    right = {0, 3, 4, 5}
    lines = []
    for n, row in enumerate(rows):
        cells = [cell.rjust(w) if c in right else cell.ljust(w) for c, (cell, w) in enumerate(zip(row, widths))]
        lines.append("  ".join(cells).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


# -- Markdown -----------------------------------------------------------
def render_markdown(offers: list[Offer], categorizer: Categorizer, title: str, generated: datetime) -> str:
    out = [f"# {title}", "", f"Genereret {generated.astimezone():%d/%m/%Y kl. %H:%M}. {len(offers)} tilbud.", ""]
    if not offers:
        return "\n".join(out + ["Ingen tilbud matcher dine valg.", ""])
    out += [
        "| # | Butik | Vare | Pris | Førpris | Rabat | Enhedspris | Kategori | Gælder |",
        "|---:|---|---|---:|---:|---:|---:|---|---|",
    ]
    for i, o in enumerate(offers, 1):
        name = o.heading.replace("|", "/")
        if o.member:
            name += f" ({o.member})"
        if o.description:
            name += f" <br><small>{_short(o.description, 60).replace('|', '/')}</small>"
        out.append(
            f"| {i} | {o.dealer} | {name} | {kr(o.price)} | {kr(o.pre_price)} | "
            f"{discount_text(o)} | {unit_price_text(o)} | "
            f"{categorizer.display_name(o.category)} | {period_text(o)} |"
        )
    return "\n".join(out) + "\n"


# -- HTML ---------------------------------------------------------------
_CSS = """
:root { --bg:#fafaf7; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#e6e4dd; --accent:#c8102e; --good:#1f7a3a; }
@media (prefers-color-scheme: dark) { :root { --bg:#161614; --fg:#ecebe6; --muted:#a3a29b; --card:#1f1f1c; --line:#33322e; --accent:#ff5a6e; --good:#5ccf7f; } }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); }
main { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
h1 { margin:0 0 4px; font-size:26px; }
.meta { color:var(--muted); margin:0 0 20px; }
.filters { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px; }
.filters button { border:1px solid var(--line); background:var(--card); color:var(--fg); border-radius:999px; padding:4px 12px; cursor:pointer; font:inherit; font-size:13px; }
.filters button.on { background:var(--fg); color:var(--bg); border-color:var(--fg); }
.label { color:var(--muted); font-size:13px; margin:12px 0 4px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px; margin-top:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; display:flex; flex-direction:column; gap:4px; }
.card img { width:100%; height:120px; object-fit:contain; background:#fff; border-radius:8px; }
.top { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:var(--muted); }
.name { font-weight:600; }
.desc { color:var(--muted); font-size:13px; }
.price { font-size:20px; font-weight:700; }
.pre { color:var(--muted); text-decoration:line-through; font-size:13px; margin-left:6px; font-weight:400; }
.badge { background:var(--accent); color:#fff; border-radius:6px; padding:1px 6px; font-weight:700; font-size:13px; }
.badge.est { background:transparent; color:var(--accent); box-shadow:inset 0 0 0 1.5px var(--accent); }
.why { color:var(--good); font-size:13px; }
.hidden { display:none; }
"""

_JS = """
const state = {store: new Set(), cat: new Set()};
document.querySelectorAll('.filters button').forEach(b => b.addEventListener('click', () => {
  const set = state[b.dataset.kind];
  set.has(b.dataset.value) ? set.delete(b.dataset.value) : set.add(b.dataset.value);
  b.classList.toggle('on');
  document.querySelectorAll('.card').forEach(c => {
    const ok = (!state.store.size || state.store.has(c.dataset.store)) && (!state.cat.size || state.cat.has(c.dataset.cat));
    c.classList.toggle('hidden', !ok);
  });
}));
"""


def render_html(offers: list[Offer], categorizer: Categorizer, title: str, generated: datetime) -> str:
    e = html.escape
    stores = sorted({o.dealer for o in offers})
    cats = sorted({o.category or "" for o in offers}, key=categorizer.display_name)

    def buttons(kind: str, values: list[str], label=lambda v: v) -> str:
        return "".join(
            f'<button data-kind="{kind}" data-value="{e(v)}">{e(label(v))}</button>' for v in values
        )

    cards = []
    for i, o in enumerate(offers, 1):
        img = f'<img src="{e(o.image_url)}" alt="" loading="lazy">' if o.image_url else ""
        pre = f'<span class="pre">{kr(o.pre_price)}</span>' if o.pre_price else ""
        est = " est" if o.discount_pct is None else ""
        badge = f'<span class="badge{est}">{discount_text(o)}</span>' if discount_text(o) else ""
        unit = f'<div class="desc">{unit_price_text(o)}</div>' if o.unit_price else ""
        why = f'<div class="why">{e(", ".join(o.reasons))}</div>' if o.reasons else ""
        member = f'<div class="desc"><b>{e(o.member)}</b></div>' if o.member else ""
        cards.append(
            f'<div class="card" data-store="{e(o.dealer)}" data-cat="{e(o.category or "")}">'
            f'{img}<div class="top"><span>#{i} · {e(o.dealer)}</span>{badge}</div>'
            f'<div class="name">{e(o.heading)}</div><div class="desc">{e(o.description)}</div>'
            f'<div class="price">{kr(o.price)}{pre}</div>{member}{unit}{why}'
            f'<div class="desc">{e(categorizer.display_name(o.category))} · {period_text(o)}</div></div>'
        )
    body = "".join(cards) if cards else "<p>Ingen tilbud matcher dine valg.</p>"
    return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><style>{_CSS}</style></head>
<body><main>
<h1>{e(title)}</h1>
<p class="meta">Genereret {generated.astimezone():%d/%m/%Y kl. %H:%M} · {len(offers)} tilbud</p>
<div class="label">Butik</div><div class="filters">{buttons("store", stores)}</div>
<div class="label">Kategori</div><div class="filters">{buttons("cat", cats, categorizer.display_name)}</div>
<div class="grid">{body}</div>
</main><script>{_JS}</script></body></html>
"""


# -- JSON ---------------------------------------------------------------
def render_json(offers: list[Offer], categorizer: Categorizer, generated: datetime) -> str:
    """Maskinlæsbar liste - tænkt som input til fx en madplan."""
    payload = {
        "generated": generated.isoformat(),
        "offers": [
            {**o.to_dict(), "category_name": categorizer.display_name(o.category)} for o in offers
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_reports(
    offers: list[Offer],
    categorizer: Categorizer,
    output_dir: Path,
    formats: list[str],
    generated: datetime,
    title: str = "Ugens bedste tilbud",
) -> list[Path]:
    """Skriver rapporter, både med dato i navnet og som 'seneste'."""
    output_dir.mkdir(parents=True, exist_ok=True)
    renderers = {
        "html": lambda: render_html(offers, categorizer, title, generated),
        "md": lambda: render_markdown(offers, categorizer, title, generated),
        "json": lambda: render_json(offers, categorizer, generated),
        "txt": lambda: render_text(offers, categorizer) + "\n",
    }
    stamp = generated.astimezone().strftime("%Y-%m-%d")
    written = []
    for fmt in formats:
        if fmt not in renderers:
            raise ValueError(f"Ukendt rapportformat: {fmt} (brug {', '.join(renderers)})")
        content = renderers[fmt]()
        for name in (f"tilbud-{stamp}.{fmt}", f"seneste.{fmt}"):
            path = output_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
    return written
