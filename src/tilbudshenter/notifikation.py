"""Besked på telefonen, når en vare man holder øje med kommer på tilbud.

Varerne står i ``notifikationer.txt`` i repoet, ét søgeord pr. linje. Når
workflowen har bygget siden, søges der efter dem i de nye tilbud med præcis
samme regler som søgningen og "Mine basisvarer" på siden (JavaScript-koden
mellem "// <search>" og "// </search>" i app.html, kørt i Node). Træffene
sendes som push-besked gennem ntfy (https://ntfy.sh), som er gratis og ikke
kræver konto: man installerer appen og abonnerer på et emne, og workflowen
sender til samme emne.

Hvilke tilbud der allerede er sendt besked om, huskes i
``notifikationer.json`` ved siden af data.json, så hvert tilbud kun giver
besked én gang.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.request
from importlib import resources
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)

DEFAULT_LIST = Path("notifikationer.txt")
STATE_NAME = "notifikationer.json"
SITE_URL = "https://simonhansen8.github.io/Tilbudshenter/"
NTFY_SERVER = "https://ntfy.sh"
# Så mange tilbud vises i én besked; resten står på siden
MAX_LINES = 6


def read_watchlist(path: Path) -> tuple[list[str], set[str] | None]:
    """Søgeordene og evt. de kæder, der skal gives besked om (None = alle)."""
    terms: list[str] = []
    stores: set[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.casefold().startswith("butikker:"):
            names = {s.strip().casefold() for s in line.split(":", 1)[1].split(",") if s.strip()}
            stores = names or None
        elif line.casefold() not in {t.casefold() for t in terms}:
            terms.append(line)
    return terms, stores


def search_block() -> str:
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    return html.split("// <search>", 1)[1].split("\n", 1)[1].split("// </search>", 1)[0]


def match_offers(terms: list[str], offers: list[dict]) -> dict[str, list[int]]:
    """For hvert søgeord numrene på de tilbud, søgningen regner for rigtige
    træf (niveau 0 og 1, som "Mine basisvarer" viser; ikke is med smag af banan).
    Ordlisten bygges af alle tilbuddene, som på siden."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node er ikke installeret; den bruges til sidens søgning")
    script = (
        f"{search_block()}\n"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
        "const offers = input.offers, idx = searchIndex(offers), out = {};\n"
        "for (const t of input.terms) {\n"
        "  const m = searchMatcher(t, idx);\n"
        "  out[t] = m ? offers.flatMap((o, i) => { const tier = m(o); return tier === 0 || tier === 1 ? [i] : []; }) : [];\n"
        "}\n"
        "console.log(JSON.stringify(out));\n"
    )
    slim = [{k: o.get(k) or "" for k in ("heading", "description", "dealer", "category")} for o in offers]
    with_input = json.dumps({"terms": terms, "offers": slim}, ensure_ascii=False)
    res = subprocess.run(
        [node, "-e", script], input=with_input, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(res.stdout)


def offer_key(o: dict) -> str:
    return str(o.get("id") or f"{o.get('dealer')}|{o.get('heading')}|{o.get('run_from')}")


def offer_line(o: dict) -> str:
    heading = " ".join(str(o.get("heading", "")).split())
    parts = [f"{o.get('dealer')}: {heading}", o.get("price_text") or ""]
    if o.get("discount_text"):
        parts.append(f"({o['discount_text']})")
    if o.get("period_text"):
        parts.append(o["period_text"])
    return " ".join(p for p in parts if p)


def message(term: str, offers: list[dict], site_url: str = SITE_URL) -> dict:
    """Beskeden til ntfy for ét søgeord (ntfy's JSON-format)."""
    lines = [offer_line(o) for o in offers[:MAX_LINES]]
    if len(offers) > MAX_LINES:
        lines.append(f"+ {len(offers) - MAX_LINES} flere på siden")
    title = f"{term[:1].upper()}{term[1:]} er på tilbud"
    if len(offers) > 1:
        title += f" ({len(offers)} tilbud)"
    return {
        "title": title,
        "message": "\n".join(lines),
        "click": f"{site_url}?q={quote(term)}",
        "tags": ["shopping_cart"],
    }


def send_ntfy(topic: str, msg: dict, server: str = NTFY_SERVER) -> None:
    body = json.dumps({"topic": topic, **msg}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(server.rstrip("/") + "/", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def load_state(path: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sent = data.get("sendt", {}) if isinstance(data, dict) else {}
    return {t: [str(k) for k in v] for t, v in sent.items() if isinstance(v, list)}


def notify(
    data: dict, terms: list[str], stores: set[str] | None, state_path: Path,
    send=None, site_url: str = SITE_URL,
) -> dict[str, list[dict]]:
    """Sender besked om de tilbud på søgeordene, der ikke er sendt besked om
    før, og husker dem. Uden ``send`` vises træffene kun (og huskes ikke).
    Returnerer de nye tilbud for hvert søgeord."""
    offers = data.get("offers", [])
    sent = load_state(state_path)
    current = {offer_key(o) for o in offers}
    hits = match_offers(terms, offers) if terms else {}
    result: dict[str, list[dict]] = {}
    new_state: dict[str, list[str]] = {}
    for term in terms:
        before = set(sent.get(term, []))
        found = [offers[i] for i in hits.get(term, [])
                 if stores is None or str(offers[i].get("dealer", "")).casefold() in stores]
        fresh = [o for o in found if offer_key(o) not in before]
        # Billigst først
        fresh.sort(key=lambda o: (o.get("price") or 0))
        result[term] = fresh
        # Udløbne tilbud glemmes, så filen ikke vokser
        keep = sorted(k for k in before if k in current)
        if fresh and send:
            try:
                send(message(term, fresh, site_url))
                keep = sorted(set(keep) | {offer_key(o) for o in fresh})
            except OSError as exc:
                log.warning("Kunne ikke sende besked om %s: %s", term, exc)
        if keep:
            new_state[term] = keep
    if send:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"sendt": new_state}, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
    return result


def run(data_path: Path, list_path: Path, state_path: Path | None = None) -> int:
    terms, stores = read_watchlist(list_path) if list_path.exists() else ([], None)
    if not terms:
        print(f"Ingen varer i {list_path}; ingen notifikationer.")
        return 0
    data = json.loads(data_path.read_text(encoding="utf-8"))
    topic = os.environ.get("NTFY_EMNE", "").strip()
    server = os.environ.get("NTFY_SERVER", "").strip() or NTFY_SERVER
    send = (lambda msg: send_ntfy(topic, msg, server)) if topic else None
    result = notify(data, terms, stores, state_path or data_path.parent / STATE_NAME, send)
    for term, offers in result.items():
        print(f"{term}: {len(offers)} nye tilbud")
        for o in offers:
            print(f"  {offer_line(o)}")
    if not topic:
        print("NTFY_EMNE er ikke sat, så der er ikke sendt nogen beskeder.")
    return 0
